"""Hybrid retriever: dense (vector DB) + sparse (BM25) fused with RRF.

Returns rich hits: {id, score, document, metadata}.
"""
from typing import List, Dict, Any, Optional
from loguru import logger

from ragh.config import settings
from ragh.embeddings.embedder import Embedder
from ragh.vectordb.base import VectorStore
from ragh.retriever.bm25 import BM25Retriever


class Retriever:
    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        bm25: Optional[BM25Retriever] = None,
    ):
        self.embedder = embedder
        self.store = store
        self.bm25 = bm25

    # ---------------- public API ----------------
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        top_k = top_k or settings.TOP_K
        dense_hits = self._dense(query, settings.RETRIEVE_K_DENSE, where)
        sparse_hits = self._sparse(query, settings.RETRIEVE_K_BM25, where)

        if not sparse_hits:
            return dense_hits[:top_k]
        if not dense_hits:
            return sparse_hits[:top_k]

        return self._rrf_fuse(dense_hits, sparse_hits, top_k=top_k)

    # ---------------- internals ----------------
    def _dense(self, query: str, k: int, where) -> List[Dict[str, Any]]:
        q_emb = self.embedder.embed_query(query)
        return self.store.search(q_emb, top_k=k, where=where)

    def _sparse(self, query: str, k: int, where) -> List[Dict[str, Any]]:
        if self.bm25 is None:
            return []
        return self.bm25.search(query, top_k=k, where=where)

    @staticmethod
    def _rrf_fuse(
        dense: List[Dict[str, Any]],
        sparse: List[Dict[str, Any]],
        top_k: int,
        rrf_k: int = None,
    ) -> List[Dict[str, Any]]:
        rrf_k = rrf_k or settings.RRF_K
        scored: Dict[str, Dict[str, Any]] = {}
        for rank, hit in enumerate(dense):
            cid = hit["id"]
            scored.setdefault(cid, {**hit, "score": 0.0, "rrf": 0.0})
            scored[cid]["rrf"] += 1.0 / (rrf_k + rank + 1)
        for rank, hit in enumerate(sparse):
            cid = hit["id"]
            scored.setdefault(cid, {**hit, "score": 0.0, "rrf": 0.0})
            scored[cid]["rrf"] += 1.0 / (rrf_k + rank + 1)
        fused = sorted(scored.values(), key=lambda x: x["rrf"], reverse=True)
        # surface RRF as the displayed score for stable ordering downstream
        for h in fused:
            h["score"] = h.pop("rrf")
        return fused[:top_k]
