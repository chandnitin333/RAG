"""Cross-encoder reranker (local). Defaults to BAAI/bge-reranker-base."""
from typing import List, Dict, Any, Optional
from sentence_transformers import CrossEncoder
from loguru import logger

from ragh.config import settings


class Reranker:
    def __init__(self, model_name: Optional[str] = None, device: str = "cpu"):
        self.model_name = model_name or settings.RERANKER_MODEL
        logger.info("Loading reranker: {}", self.model_name)
        self.model = CrossEncoder(self.model_name, device=device)

    def rerank(
        self,
        query: str,
        hits: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if not hits:
            return hits
        pairs = [(query, h["document"]) for h in hits]
        scores = self.model.predict(pairs, show_progress_bar=False)
        for h, s in zip(hits, scores):
            h["rerank_score"] = float(s)
        ranked = sorted(hits, key=lambda x: x["rerank_score"], reverse=True)
        k = top_k or settings.RERANK_TOP_K
        return ranked[:k]
