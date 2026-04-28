"""Chroma-backed vector store. Embedded, persistent, no server required."""
from typing import List, Dict, Optional, Any
import numpy as np
import chromadb
from chromadb.config import Settings as ChromaSettings
from loguru import logger

from ragh.config import settings
from ragh.vectordb.base import VectorStore


class ChromaStore(VectorStore):
    def __init__(self, collection_name: Optional[str] = None):
        self.collection_name = collection_name or settings.CHROMA_COLLECTION
        self.client = chromadb.PersistentClient(
            path=str(settings.CHROMA_DIR),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        # cosine + custom embeddings (we provide vectors directly, no embedding fn)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaStore ready: collection={} count={}",
            self.collection_name,
            self.collection.count(),
        )

    def add(
        self,
        ids: List[str],
        embeddings: np.ndarray,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        if len(ids) == 0:
            return
        # Chroma requires lists, scalar metadata values
        clean_meta = [_clean_meta(m) for m in metadatas]
        self.collection.add(
            ids=ids,
            embeddings=embeddings.astype(np.float32).tolist(),
            documents=documents,
            metadatas=clean_meta,
        )
        logger.debug("Chroma add: {} vectors", len(ids))

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        q = query_embedding.astype(np.float32)
        if q.ndim == 1:
            q = q.reshape(1, -1)
        kwargs: Dict[str, Any] = {
            "query_embeddings": q.tolist(),
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        res = self.collection.query(**kwargs)
        results: List[Dict[str, Any]] = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for _id, doc, meta, dist in zip(ids, docs, metas, dists):
            # cosine distance → similarity
            score = 1.0 - float(dist)
            results.append(
                {"id": _id, "score": score, "document": doc, "metadata": meta or {}}
            )
        return results

    def get_all_documents(self) -> List[Dict[str, Any]]:
        # Chroma's .get() with no ids returns everything (page-fetched internally).
        res = self.collection.get(include=["documents", "metadatas"])
        out = []
        for _id, doc, meta in zip(
            res.get("ids", []), res.get("documents", []), res.get("metadatas", [])
        ):
            out.append({"id": _id, "document": doc, "metadata": meta or {}})
        return out

    def count(self) -> int:
        return self.collection.count()

    def delete_by_source(self, source_file: str) -> int:
        before = self.count()
        self.collection.delete(where={"source_file": source_file})
        after = self.count()
        return max(0, before - after)


def _clean_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Chroma only accepts str/int/float/bool. Coerce or drop other values."""
    out: Dict[str, Any] = {}
    for k, v in meta.items():
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif v is None:
            continue
        else:
            out[k] = str(v)
    return out
