"""In-memory BM25 keyword retriever, rebuilt from the vector store on demand.

For corpora up to ~1M chunks this stays cheap. Persists tokenized cache to disk.
"""
from typing import List, Dict, Any, Optional
from pathlib import Path
import pickle
import re
from rank_bm25 import BM25Okapi
from loguru import logger

from ragh.config import settings


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


class BM25Retriever:
    def __init__(self, cache_path: Optional[Path] = None):
        self.cache_path = Path(cache_path or (settings.INDEX_DIR / "bm25_cache.pkl"))
        self.bm25: Optional[BM25Okapi] = None
        self.records: List[Dict[str, Any]] = []  # [{id, document, metadata}, ...]

    def build(self, records: List[Dict[str, Any]]) -> None:
        self.records = records
        if not records:
            self.bm25 = None
            return
        corpus = [tokenize(r["document"]) for r in records]
        self.bm25 = BM25Okapi(corpus)
        self._save()
        logger.info("BM25 built over {} chunks", len(records))

    def search(
        self,
        query: str,
        top_k: int = 30,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if self.bm25 is None or not self.records:
            return []
        scores = self.bm25.get_scores(tokenize(query))
        ranked_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        out: List[Dict[str, Any]] = []
        for i in ranked_idx:
            if scores[i] <= 0:
                break
            rec = self.records[i]
            if where and not _matches(rec.get("metadata") or {}, where):
                continue
            out.append({
                "id": rec["id"],
                "score": float(scores[i]),
                "document": rec["document"],
                "metadata": rec.get("metadata") or {},
            })
            if len(out) >= top_k:
                break
        return out

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "wb") as f:
            pickle.dump({"bm25": self.bm25, "records": self.records}, f)

    def load(self) -> bool:
        if not self.cache_path.exists():
            return False
        try:
            with open(self.cache_path, "rb") as f:
                blob = pickle.load(f)
            self.bm25 = blob["bm25"]
            self.records = blob["records"]
            logger.info("BM25 loaded from cache: {} chunks", len(self.records))
            return True
        except Exception as e:
            logger.warning("BM25 cache load failed: {}", e)
            return False


def _matches(meta: Dict[str, Any], where: Dict[str, Any]) -> bool:
    for k, v in where.items():
        if meta.get(k) != v:
            return False
    return True
