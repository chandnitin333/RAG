"""Ollama-backed reader. Local LLM via http://127.0.0.1:11434.

Far better answer quality than flan-t5 for RAG. Default model: llama3.2:3b.
Install: `brew install ollama` then `ollama pull llama3.2:3b`.
"""
from typing import List, Dict, Any
import json
import urllib.request
import urllib.error
from loguru import logger

from ragh.config import settings
from ragh.utils.symbol_remap import remap_lite_cleanup


SYSTEM_PROMPT = (
    "You are a helpful study assistant for JEE-level physics, chemistry, and "
    "math. Answer using ONLY the provided context excerpts. Cite excerpt "
    "numbers inline like [1], [2] for any specific fact, formula, or example "
    "you use.\n\n"
    "EXACT CONTENT: When the user asks for definitions, statements, formulas, "
    "or 'what does the book say', quote the relevant sentences from the "
    "context VERBATIM inside a fenced quote block, then add your explanation. "
    "Do not paraphrase the canonical statement.\n\n"
    "FORMAT: Match the user's requested format exactly — JSON / list / table / "
    "prose. If they ask for JSON, output valid JSON only.\n\n"
    "DIAGRAMS: If the user asks for a diagram, figure, drawing, sketch, plot, "
    "or asks you to 'draw' something, produce a self-contained SVG inside a "
    "```svg fenced code block. The SVG must:\n"
    "  - have a viewBox attribute and width=\"100%\"\n"
    "  - use stroke=\"#111\" or similar dark colors so it's visible on a light bg\n"
    "  - include axis/labels via <text> elements\n"
    "  - be no larger than 600x500\n"
    "For flowcharts/relationships, you may use a ```mermaid block instead.\n"
    "Always follow the diagram with a one-line caption.\n\n"
    "MATH: PDF source text often has garbled math (broken spacing, Symbol-font "
    "glyphs, stray digits). Silently reconstruct it into clean standard "
    "notation when quoting or paraphrasing.\n\n"
    "If the answer is genuinely not in the context, say 'Not found in the "
    "provided documents.' and stop."
)


class OllamaReader:
    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        num_ctx: int = 4096,
        temperature: float = 0.2,
    ):
        self.model = model or settings.OLLAMA_MODEL
        self.base_url = (base_url or settings.OLLAMA_URL).rstrip("/")
        self.num_ctx = num_ctx
        self.temperature = temperature
        logger.info("OllamaReader: {} @ {}", self.model, self.base_url)

    @staticmethod
    def is_available(base_url: str) -> bool:
        try:
            req = urllib.request.Request(f"{base_url.rstrip('/')}/api/tags")
            with urllib.request.urlopen(req, timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    def answer(
        self,
        question: str,
        hits: List[Dict[str, Any]],
        max_len: int = 768,  # max output tokens
    ) -> Dict[str, Any]:
        if not hits:
            return {
                "answer": "I couldn't find anything relevant in the indexed documents.",
                "citations": [],
                "mode": "ollama",
            }

        contexts = [h["document"] for h in hits]
        numbered = "\n\n".join(f"[{i+1}] {c}" for i, c in enumerate(contexts))
        user_prompt = (
            f"Context excerpts:\n{numbered}\n\n"
            f"User request: {question}\n\n"
            "Follow the user's requested format precisely. Cite excerpt numbers "
            "inline (e.g. [1], [3]). Reconstruct any garbled math into clean "
            "standard notation."
        )

        body = {
            "model": self.model,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
                "num_predict": max_len,
            },
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                payload = json.loads(r.read().decode("utf-8"))
            content = (payload.get("message") or {}).get("content", "").strip()
        except urllib.error.URLError as e:
            logger.exception("Ollama call failed: {}", e)
            return {
                "answer": f"LLM call failed: {e}",
                "citations": _build_citations(hits),
                "mode": "ollama-error",
            }

        return {
            "answer": content or "Not found in the provided documents.",
            "citations": _build_citations(hits),
            "mode": "ollama",
        }


def _build_citations(hits) -> List[Dict[str, Any]]:
    """Return one entry per retrieved chunk. Exposes the full chunk text plus
    multimodal metadata (image_url for image chunks)."""
    out = []
    for i, h in enumerate(hits):
        meta = h.get("metadata") or {}
        raw = h.get("document") or ""
        cleaned = remap_lite_cleanup(raw)
        out.append({
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
            # multimodal:
            "kind": meta.get("kind", "text"),
            "image_url": meta.get("image_url"),
            "page": meta.get("page"),
            "ocr_text": meta.get("ocr_text"),
        })
    return out
