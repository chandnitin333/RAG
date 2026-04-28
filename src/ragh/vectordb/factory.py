"""Factory for choosing the vector DB backend at runtime."""
from loguru import logger

from ragh.config import settings
from ragh.vectordb.base import VectorStore


def get_vector_store(dim: int) -> VectorStore:
    backend = settings.VECTOR_DB.lower()
    if backend == "chroma":
        from ragh.vectordb.chroma_store import ChromaStore
        return ChromaStore()
    if backend == "faiss":
        from ragh.vectordb.faiss_store import FaissStore
        return FaissStore(dim=dim)
    if backend == "milvus":
        from ragh.vectordb.milvus_store import MilvusStore
        return MilvusStore(dim=dim)
    logger.warning("Unknown VECTOR_DB={}, falling back to chroma", backend)
    from ragh.vectordb.chroma_store import ChromaStore
    return ChromaStore()
