"""FAISS-backed vector store with a SQLite sidecar for chunk text + metadata.

Production note: FAISS itself does not store text/metadata. We mirror them in
SQLite so retrieval returns full content + provenance, not just vector IDs.
"""
from pathlib import Path
from typing import List, Dict, Optional, Any
import json
import sqlite3
import numpy as np
import faiss
from loguru import logger

from ragh.config import settings
from ragh.vectordb.base import VectorStore


class FaissStore(VectorStore):
    def __init__(self, dim: int, index_path: Optional[Path] = None):
        self.dim = dim
        self.index_path = Path(index_path or settings.FAISS_INDEX_PATH)
        self.meta_path = self.index_path.with_suffix(".sqlite")
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_sqlite()
        self._init_index()
        logger.info("FaissStore ready: dim={} count={}", dim, self.count())

    # ------------- init -------------
    def _init_sqlite(self):
        self.conn = sqlite3.connect(str(self.meta_path), check_same_thread=False)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id TEXT UNIQUE NOT NULL,
                document TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                source_file TEXT
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_source ON chunks(source_file)"
        )
        self.conn.commit()

    def _init_index(self):
        if self.index_path.exists():
            self.index = faiss.read_index(str(self.index_path))
        else:
            self.index = faiss.IndexFlatIP(self.dim)

    # ------------- VectorStore impl -------------
    def add(
        self,
        ids: List[str],
        embeddings: np.ndarray,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        if len(ids) == 0:
            return
        assert embeddings.shape[1] == self.dim
        self.index.add(embeddings.astype(np.float32))
        cur = self.conn.cursor()
        rows = [
            (cid, doc, json.dumps(meta), meta.get("source_file"))
            for cid, doc, meta in zip(ids, documents, metadatas)
        ]
        cur.executemany(
            "INSERT OR REPLACE INTO chunks(chunk_id, document, metadata_json, source_file) VALUES (?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        q = query_embedding.astype(np.float32)
        if q.ndim == 1:
            q = q.reshape(1, -1)
        # over-fetch when filtering (FAISS can't filter natively)
        fetch = top_k * 5 if where else top_k
        D, I = self.index.search(q, fetch)
        results: List[Dict[str, Any]] = []
        cur = self.conn.cursor()
        for idx, score in zip(I[0], D[0]):
            if idx < 0:
                continue
            row = cur.execute(
                "SELECT chunk_id, document, metadata_json FROM chunks WHERE row_id=?",
                (int(idx) + 1,),  # SQLite AUTOINCREMENT is 1-based
            ).fetchone()
            if not row:
                continue
            cid, doc, meta_json = row
            meta = json.loads(meta_json)
            if where and not _matches(meta, where):
                continue
            results.append(
                {"id": cid, "score": float(score), "document": doc, "metadata": meta}
            )
            if len(results) >= top_k:
                break
        return results

    def get_all_documents(self) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        rows = cur.execute(
            "SELECT chunk_id, document, metadata_json FROM chunks"
        ).fetchall()
        return [
            {"id": cid, "document": doc, "metadata": json.loads(meta)}
            for cid, doc, meta in rows
        ]

    def count(self) -> int:
        return int(self.index.ntotal)

    def delete_by_source(self, source_file: str) -> int:
        # FAISS IndexFlat doesn't support deletes cleanly. We mark in SQLite and
        # let a future rebuild compact. Returns rows marked.
        cur = self.conn.cursor()
        cur.execute(
            "DELETE FROM chunks WHERE source_file=?", (source_file,)
        )
        n = cur.rowcount
        self.conn.commit()
        logger.warning(
            "FAISS delete_by_source removed {} sqlite rows; vector index not compacted (run rebuild).",
            n,
        )
        return n

    def persist(self) -> None:
        faiss.write_index(self.index, str(self.index_path))
        self.conn.commit()


def _matches(meta: Dict[str, Any], where: Dict[str, Any]) -> bool:
    for k, v in where.items():
        if meta.get(k) != v:
            return False
    return True
