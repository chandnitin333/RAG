"""Unified VectorStore interface. Backends: chroma, faiss, milvus."""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
import numpy as np


class VectorStore(ABC):
    @abstractmethod
    def add(
        self,
        ids: List[str],
        embeddings: np.ndarray,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """Insert vectors with their text + metadata."""

    @abstractmethod
    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Return list of {id, score, document, metadata}, sorted by score desc."""

    @abstractmethod
    def get_all_documents(self) -> List[Dict[str, Any]]:
        """Return all stored {id, document, metadata} — used to (re)build BM25."""

    @abstractmethod
    def count(self) -> int:
        """Number of indexed chunks."""

    @abstractmethod
    def delete_by_source(self, source_file: str) -> int:
        """Remove all chunks coming from a given source file. Returns count removed."""

    def persist(self) -> None:
        """Optional: flush to disk. Default no-op (Chroma persists automatically)."""
        return None
