"""Multi-turn chat pipeline:

  1. Query rewrite — clean up the user's latest message into a well-formed
     standalone search question (handles broken English, follow-ups like
     "and the next one?", typos).
  2. Hybrid retrieve (Chroma + BM25, RRF fused).
  3. Optional cross-encoder rerank.
  4. Answer generation with full conversation history (Ollama-based reader).
"""
from typing import List, Dict, Any, Optional, Iterator
import json
import urllib.request
import urllib.error
from loguru import logger

from ragh.config import settings
from ragh.retriever.retriever import Retriever
from ragh.retriever.reranker import Reranker
from ragh.reader.ollama_reader import OllamaReader, SYSTEM_PROMPT, _build_citations
from ragh.pipeline.agents import route as route_agent, system_prompt_for, display_label
from ragh.utils.symbol_remap import remap_lite_cleanup


REWRITE_SYSTEM = (
    "You rewrite student questions into a single well-formed English search "
    "query for a study-material search engine. Resolve pronouns and follow-ups "
    "by using prior conversation turns. Fix typos and grammar. Keep the "
    "subject-specific terms. Output ONLY the rewritten search query, no quotes, "
    "no preamble, one line."
)


class ChatPipeline:
    def __init__(
        self,
        retriever: Retriever,
        reader: OllamaReader,
        reranker: Optional[Reranker] = None,
    ):
        self.retriever = retriever
        self.reader = reader
        self.reranker = reranker

    def chat(
        self,
        messages: List[Dict[str, str]],
        top_k: Optional[int] = None,
        where: Optional[Dict[str, Any]] = None,
        agent_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not messages:
            raise ValueError("messages must not be empty")
        latest_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        if not latest_user.strip():
            raise ValueError("latest user message is empty")

        # 1. rewrite
        corrected = self._rewrite(messages, latest_user)
        logger.info("Rewrote: {!r} -> {!r}", latest_user, corrected)

        # 2. route
        agent = agent_override or route_agent(latest_user)

        # 3. retrieve
        top_k = top_k or settings.TOP_K
        fetch_n = max(top_k, settings.RERANK_TOP_K) if self.reranker else top_k
        hits = self.retriever.retrieve(corrected, top_k=fetch_n, where=where)

        # 4. rerank
        if self.reranker and hits:
            hits = self.reranker.rerank(corrected, hits, top_k=top_k)
        else:
            hits = hits[:top_k]

        # 5. answer with conversation history + agent-specific system prompt
        answer = self._answer_with_history(messages, corrected, hits, agent=agent)

        return {
            "answer": answer,
            "corrected_query": corrected,
            "agent": agent,
            "agent_label": display_label(agent),
            "mode": "chat",
            "citations": _build_citations(hits),
            "retrieved": [
                {
                    "id": h["id"],
                    "score": h.get("rerank_score", h.get("score")),
                    "preview": (h.get("document") or "")[:240],
                    "metadata": h.get("metadata", {}),
                }
                for h in hits
            ],
        }

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        top_k: Optional[int] = None,
        where: Optional[Dict[str, Any]] = None,
        agent_override: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yields events as dicts: {type, data}.
        Event types: corrected, agent, retrieved, citations, token, done, error.
        """
        try:
            if not messages:
                raise ValueError("messages must not be empty")
            latest_user = next(
                (m["content"] for m in reversed(messages) if m.get("role") == "user"),
                "",
            )
            if not latest_user.strip():
                raise ValueError("latest user message is empty")

            corrected = self._rewrite(messages, latest_user)
            yield {"type": "corrected", "data": corrected}

            agent = agent_override or route_agent(latest_user)
            yield {"type": "agent", "data": {"agent": agent, "label": display_label(agent)}}

            top_k_i = top_k or settings.TOP_K
            fetch_n = max(top_k_i, settings.RERANK_TOP_K) if self.reranker else top_k_i
            hits = self.retriever.retrieve(corrected, top_k=fetch_n, where=where)
            if self.reranker and hits:
                hits = self.reranker.rerank(corrected, hits, top_k=top_k_i)
            else:
                hits = hits[:top_k_i]

            citations = _build_citations(hits)
            yield {"type": "citations", "data": citations}

            for tok in self._stream_answer(messages, corrected, hits, agent=agent):
                yield {"type": "token", "data": tok}
            yield {"type": "done", "data": {"agent": agent}}
        except Exception as e:
            logger.exception("chat_stream failed: {}", e)
            yield {"type": "error", "data": str(e)}

    # ---------------- internals ----------------
    def _rewrite(self, messages: List[Dict[str, str]], latest_user: str) -> str:
        # only use the last few turns to keep prompt small
        history = messages[-6:]
        rendered = "\n".join(f"{m['role']}: {m['content']}" for m in history)
        body = {
            "model": self.reader.model,
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 96},
            "messages": [
                {"role": "system", "content": REWRITE_SYSTEM},
                {"role": "user", "content": f"Conversation so far:\n{rendered}\n\nLatest user message: {latest_user}\n\nRewrite as a standalone English search query."},
            ],
        }
        return self._ollama_chat(body, fallback=latest_user)

    @staticmethod
    def _ollama_options_for(agent: str) -> Dict[str, Any]:
        """Per-agent Ollama options. Quizzer uses JSON output mode."""
        opts: Dict[str, Any] = {}
        if agent == "quizzer":
            # `format: "json"` — Ollama constrains output to valid JSON.
            # Schema is enforced via the prompt's few-shot example (the
            # strict-schema mode confuses small models like Llama 3.2 3B).
            opts["format"] = "json"
            opts["temperature_override"] = 0.0
        return opts

    def _build_chat_messages(
        self,
        messages: List[Dict[str, str]],
        corrected: str,
        hits: List[Dict[str, Any]],
        agent: str = "teacher",
    ) -> List[Dict[str, str]]:
        if not hits:
            return [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": corrected},
            ]
        contexts = [remap_lite_cleanup(h["document"]) for h in hits]
        numbered = "\n\n".join(f"[{i+1}] {c}" for i, c in enumerate(contexts))
        sys = system_prompt_for(agent)
        chat: List[Dict[str, str]] = [{"role": "system", "content": sys}]
        prior = list(messages[:-1])
        chat.extend(prior[-6:])

        # Quizzer needs its strict shape repeated right before generation —
        # small models (Llama 3.2 3B) ignore the system-prompt example
        # otherwise.
        if agent == "quizzer":
            quizzer_user = (
                f"Context excerpts:\n{numbered}\n\n"
                f"User request: {corrected}\n\n"
                "Produce exactly 5 Level-1 multiple-choice questions about "
                "this topic, drawn from the context.\n\n"
                "Output a SINGLE JSON object. The object has ONE key "
                "(\"questions\") whose value is an array containing all 5 "
                "questions. DO NOT repeat the outer object for each question. "
                "DO NOT use any keys other than the ones shown.\n\n"
                "Required shape (5 entries inside the same array):\n\n"
                "{\n"
                '  "questions": [\n'
                "    {\n"
                '      "question": "Stem of question 1?",\n'
                '      "options": {"A": "...", "B": "...", "C": "...", "D": "..."},\n'
                '      "correct": "A",\n'
                '      "explanation": "Why A is correct.",\n'
                '      "difficulty": "Level-1"\n'
                "    },\n"
                "    {\n"
                '      "question": "Stem of question 2?",\n'
                '      "options": {"A": "...", "B": "...", "C": "...", "D": "..."},\n'
                '      "correct": "C",\n'
                '      "explanation": "Why C is correct.",\n'
                '      "difficulty": "Level-1"\n'
                "    },\n"
                "    { /* question 3, same shape */ },\n"
                "    { /* question 4, same shape */ },\n"
                "    { /* question 5, same shape */ }\n"
                "  ]\n"
                "}\n\n"
                "REMINDER: ONE \"questions\" key total, not five. The array "
                "contains 5 elements."
            )
            chat.append({"role": "user", "content": quizzer_user})
        else:
            chat.append({
                "role": "user",
                "content": (
                    f"Context excerpts:\n{numbered}\n\n"
                    f"My question (cleaned): {corrected}\n\n"
                    "Follow your agent role exactly. Reconstruct any garbled "
                    "math into clean LaTeX. Do NOT add a final 'Note:' line "
                    "or any [n] citation markers in the answer body."
                ),
            })
        return chat

    def _answer_with_history(
        self,
        messages: List[Dict[str, str]],
        corrected: str,
        hits: List[Dict[str, Any]],
        agent: str = "teacher",
    ) -> str:
        if not hits:
            return "I couldn't find anything relevant in the indexed documents for that question."
        agent_opts = self._ollama_options_for(agent)
        body: Dict[str, Any] = {
            "model": self.reader.model,
            "stream": False,
            "options": {
                "temperature": agent_opts.get("temperature_override", self.reader.temperature),
                "num_ctx": self.reader.num_ctx,
                "num_predict": 2048 if agent == "quizzer" else 1024,
            },
            "messages": self._build_chat_messages(messages, corrected, hits, agent=agent),
        }
        if "format" in agent_opts:
            body["format"] = agent_opts["format"]
        return self._ollama_chat(body, fallback="(LLM call failed)")

    def _stream_answer(
        self,
        messages: List[Dict[str, str]],
        corrected: str,
        hits: List[Dict[str, Any]],
        agent: str = "teacher",
    ) -> Iterator[str]:
        """Yields content chunks as Ollama emits them."""
        if not hits:
            yield "I couldn't find anything relevant in the indexed documents for that question."
            return
        agent_opts = self._ollama_options_for(agent)
        body: Dict[str, Any] = {
            "model": self.reader.model,
            "stream": True,
            "options": {
                "temperature": agent_opts.get("temperature_override", self.reader.temperature),
                "num_ctx": self.reader.num_ctx,
                "num_predict": 2048 if agent == "quizzer" else 1024,
            },
            "messages": self._build_chat_messages(messages, corrected, hits, agent=agent),
        }
        if "format" in agent_opts:
            body["format"] = agent_opts["format"]
        req = urllib.request.Request(
            f"{self.reader.base_url}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                for raw in r:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    msg = ev.get("message") or {}
                    chunk = msg.get("content")
                    if chunk:
                        yield chunk
                    if ev.get("done"):
                        break
        except urllib.error.URLError as e:
            logger.exception("Ollama stream failed: {}", e)
            yield f"\n\n[stream failed: {e}]"

    def _ollama_chat(self, body: Dict[str, Any], fallback: str) -> str:
        req = urllib.request.Request(
            f"{self.reader.base_url}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                payload = json.loads(r.read().decode("utf-8"))
            return ((payload.get("message") or {}).get("content") or "").strip() or fallback
        except urllib.error.URLError as e:
            logger.exception("Ollama call failed: {}", e)
            return fallback
