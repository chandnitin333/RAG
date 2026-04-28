"""Local self-hosted reader. Two modes:

  - "generative": flan-t5 generates an answer grounded in retrieved chunks.
  - "extractive": returns the most salient sentences from the contexts, with
    inline citations like [1], [2]. No model needed beyond the embedder.

Switch via Reader(mode=...). Default is "generative".
"""
from typing import List, Dict, Any, Optional
import re
from loguru import logger

from ragh.config import settings


class Reader:
    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        mode: str = "generative",
    ):
        self.mode = mode
        self.model_name = model_name or settings.READER_MODEL
        self.device = device or settings.READER_DEVICE
        self.tokenizer = None
        self.model = None
        if self.mode == "generative":
            self._load_generator()

    def _load_generator(self) -> None:
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        logger.info("Loading reader model {} on {}", self.model_name, self.device)
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name).to(self.device)

    # --------------- public ---------------
    def answer(
        self,
        question: str,
        hits: List[Dict[str, Any]],
        max_len: int = 384,
    ) -> Dict[str, Any]:
        if not hits:
            return {
                "answer": "I couldn't find anything relevant in the indexed documents.",
                "citations": [],
                "mode": self.mode,
            }
        if self.mode == "extractive":
            return self._extractive(question, hits)
        return self._generative(question, hits, max_len=max_len)

    # --------------- generative ---------------
    def _generative(self, question: str, hits, max_len: int) -> Dict[str, Any]:
        contexts = [h["document"] for h in hits]
        prompt = self._build_prompt(question, contexts)
        inputs = self.tokenizer(
            prompt, return_tensors="pt", truncation=True, max_length=1024
        ).to(self.device)
        outputs = self.model.generate(
            **inputs,
            max_length=max_len,
            num_beams=4,
            no_repeat_ngram_size=3,
            early_stopping=True,
        )
        ans = self.tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
        return {
            "answer": ans,
            "citations": _build_citations(hits),
            "mode": "generative",
        }

    def _build_prompt(self, question: str, contexts: List[str]) -> str:
        numbered = "\n\n".join(f"[{i+1}] {c}" for i, c in enumerate(contexts))
        return (
            "You are a helpful assistant. Use ONLY the context to answer. "
            "Cite sources inline like [1], [2]. If the answer is not in the context, "
            "say 'Not found in the provided documents.'\n\n"
            f"Context:\n{numbered}\n\n"
            f"Question: {question}\n"
            "Answer:"
        )

    # --------------- extractive ---------------
    def _extractive(self, question: str, hits, max_sentences: int = 5) -> Dict[str, Any]:
        q_terms = set(_tokenize(question))
        scored = []
        for i, h in enumerate(hits):
            for sent in _split_sentences(h["document"]):
                terms = set(_tokenize(sent))
                overlap = len(q_terms & terms)
                if overlap == 0:
                    continue
                scored.append((overlap, i + 1, sent))
        scored.sort(reverse=True)
        picked = scored[:max_sentences]
        if not picked:
            return {
                "answer": "Not found in the provided documents.",
                "citations": _build_citations(hits),
                "mode": "extractive",
            }
        answer = " ".join(f"{s} [{idx}]" for _, idx, s in picked)
        return {
            "answer": answer,
            "citations": _build_citations(hits),
            "mode": "extractive",
        }


# --------------- helpers ---------------
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TOKEN = re.compile(r"[A-Za-z0-9]+")


def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text or "") if s.strip()]


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def _build_citations(hits) -> List[Dict[str, Any]]:
    from ragh.utils.symbol_remap import remap_lite_cleanup
    citations = []
    for i, h in enumerate(hits):
        meta = h.get("metadata") or {}
        cleaned = remap_lite_cleanup(h.get("document") or "")
        citations.append({
            "index": i + 1,
            "id": h.get("id"),
            "score": h.get("rerank_score", h.get("score")),
            "source_file": meta.get("source_file"),
            "subject": meta.get("subject"),
            "book": meta.get("book"),
            "chapter": meta.get("chapter"),
            "start_char": meta.get("start_char"),
            "end_char": meta.get("end_char"),
            "preview": cleaned[:240],
            "content": cleaned,
            "kind": meta.get("kind", "text"),
            "image_url": meta.get("image_url"),
            "page": meta.get("page"),
            "ocr_text": meta.get("ocr_text"),
        })
    return citations
