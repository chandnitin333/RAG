"""End-to-end RAG pipeline: hybrid retrieve → rerank → read."""
from typing import List, Dict, Any, Optional
from loguru import logger

from ragh.config import settings
from ragh.retriever.retriever import Retriever
from ragh.retriever.reranker import Reranker
from ragh.reader.reader import Reader


class RAGPipeline:
    def __init__(
        self,
        retriever: Retriever,
        reader: Reader,
        reranker: Optional[Reranker] = None,
    ):
        self.retriever = retriever
        self.reader = reader
        self.reranker = reranker

    def query(
        self,
        question: str,
        top_k: Optional[int] = None,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        top_k = top_k or settings.TOP_K
        logger.info("Query: {!r} top_k={} where={}", question, top_k, where)

        # 1. retrieve (hybrid) — over-fetch when a reranker is in play
        fetch_n = max(top_k, settings.RERANK_TOP_K) if self.reranker else top_k
        hits = self.retriever.retrieve(question, top_k=fetch_n, where=where)

        # 2. rerank
        if self.reranker and hits:
            hits = self.reranker.rerank(question, hits, top_k=top_k)
        else:
            hits = hits[:top_k]

        # 3. read
        result = self.reader.answer(question, hits)

        return {
            "answer": result["answer"],
            "mode": result.get("mode"),
            "citations": result.get("citations", []),
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
