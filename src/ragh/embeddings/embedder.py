"""Sentence embedder. Defaults to BAAI/bge-small-en-v1.5 (384-dim, fast)."""
from typing import List, Optional
import numpy as np
from sentence_transformers import SentenceTransformer
from loguru import logger

from ragh.config import settings


# bge models recommend a query prefix; for non-bge models we leave it empty.
_QUERY_PREFIX_BY_MODEL = {
    "BAAI/bge-small-en-v1.5": "Represent this sentence for searching relevant passages: ",
    "BAAI/bge-base-en-v1.5": "Represent this sentence for searching relevant passages: ",
    "BAAI/bge-large-en-v1.5": "Represent this sentence for searching relevant passages: ",
}


class Embedder:
    def __init__(self, model_name: Optional[str] = None, device: str = "cpu"):
        self.model_name = model_name or settings.EMBEDDING_MODEL
        logger.info("Loading embedder: {}", self.model_name)
        self.model = SentenceTransformer(self.model_name, device=device)
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        self.query_prefix = _QUERY_PREFIX_BY_MODEL.get(self.model_name, "")
        logger.info("Embedder ready: dim={} prefix={!r}", self.embedding_dim, self.query_prefix)

    def embed_texts(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        embs = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return embs.astype(np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        prefixed = self.query_prefix + query if self.query_prefix else query
        emb = self.model.encode(
            [prefixed],
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return emb.astype(np.float32)[0]
