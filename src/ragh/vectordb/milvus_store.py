"""Milvus-backed vector store. Requires Milvus running (see docker-compose.yml).

Use this when you need a real distributed vector DB. Default backend is Chroma.
"""
from typing import List, Dict, Optional, Any
import numpy as np
from loguru import logger

from ragh.config import settings
from ragh.vectordb.base import VectorStore

try:
    from pymilvus import (
        connections,
        Collection,
        CollectionSchema,
        FieldSchema,
        DataType,
        utility,
    )
    _MILVUS_OK = True
except Exception as e:  # pragma: no cover
    _MILVUS_OK = False
    _IMPORT_ERR = e


class MilvusStore(VectorStore):
    def __init__(self, dim: int, collection_name: Optional[str] = None):
        if not _MILVUS_OK:
            raise RuntimeError(f"pymilvus not available: {_IMPORT_ERR}")
        self.dim = dim
        self.collection_name = collection_name or settings.MILVUS_COLLECTION
        connections.connect(
            alias="default",
            host=settings.MILVUS_HOST,
            port=str(settings.MILVUS_PORT),
        )
        self.collection = self._ensure_collection()
        self.collection.load()
        logger.info("MilvusStore ready: collection={}", self.collection_name)

    def _ensure_collection(self) -> "Collection":
        if utility.has_collection(self.collection_name):
            return Collection(self.collection_name)
        fields = [
            FieldSchema(name="row_id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="document", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="source_file", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="subject", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="book", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="chapter", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.dim),
        ]
        schema = CollectionSchema(fields=fields, description="ragh corpus")
        col = Collection(name=self.collection_name, schema=schema)
        col.create_index(
            field_name="embedding",
            index_params={
                "index_type": "HNSW",
                "metric_type": "COSINE",
                "params": {"M": 16, "efConstruction": 200},
            },
        )
        return col

    def add(self, ids, embeddings, documents, metadatas):
        if len(ids) == 0:
            return
        rows = {
            "chunk_id": ids,
            "document": [d[:8000] for d in documents],
            "source_file": [m.get("source_file", "") for m in metadatas],
            "subject": [str(m.get("subject", ""))[:60] for m in metadatas],
            "book": [str(m.get("book", ""))[:500] for m in metadatas],
            "chapter": [str(m.get("chapter", ""))[:500] for m in metadatas],
            "embedding": embeddings.astype(np.float32).tolist(),
        }
        self.collection.insert(rows)
        self.collection.flush()

    def search(self, query_embedding, top_k=5, where=None):
        q = query_embedding.astype(np.float32)
        if q.ndim == 1:
            q = q.reshape(1, -1)
        expr = _build_expr(where) if where else None
        res = self.collection.search(
            data=q.tolist(),
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"ef": 64}},
            limit=top_k,
            expr=expr,
            output_fields=["chunk_id", "document", "source_file", "subject", "book", "chapter"],
        )
        out: List[Dict[str, Any]] = []
        for hit in res[0]:
            out.append({
                "id": hit.entity.get("chunk_id"),
                "score": float(hit.score),
                "document": hit.entity.get("document"),
                "metadata": {
                    "source_file": hit.entity.get("source_file"),
                    "subject": hit.entity.get("subject"),
                    "book": hit.entity.get("book"),
                    "chapter": hit.entity.get("chapter"),
                },
            })
        return out

    def get_all_documents(self):
        logger.warning(
            "MilvusStore.get_all_documents not implemented; BM25 hybrid disabled for milvus backend."
        )
        return []

    def count(self) -> int:
        return self.collection.num_entities

    def delete_by_source(self, source_file: str) -> int:
        expr = f'source_file == "{source_file}"'
        before = self.count()
        self.collection.delete(expr)
        self.collection.flush()
        return max(0, before - self.count())


def _build_expr(where: Dict[str, Any]) -> str:
    parts = []
    for k, v in where.items():
        if isinstance(v, str):
            parts.append(f'{k} == "{v}"')
        else:
            parts.append(f"{k} == {v}")
    return " and ".join(parts)
