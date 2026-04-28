"""SQLite-backed store for chat interactions + user feedback.

The point: turn user feedback into a stream of high-quality (Q, A) pairs we
can fine-tune the local LLM on (LoRA). Positive examples → keep verbatim.
Negative examples with a corrected answer → also keep, mark as preferred.
"""
from typing import List, Dict, Any, Optional
from pathlib import Path
import sqlite3
import json
import time
from loguru import logger

from ragh.config import settings


class FeedbackStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or (settings.INDEX_DIR / "feedback.sqlite"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._init()

    def _init(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            interaction_id TEXT,
            user_id TEXT,
            question TEXT NOT NULL,
            corrected_query TEXT,
            answer TEXT NOT NULL,
            citations_json TEXT,
            subject TEXT,
            book TEXT,
            chapter TEXT
        );
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            interaction_id TEXT NOT NULL,
            rating INTEGER NOT NULL,        -- +1 thumbs up, -1 thumbs down
            corrected_answer TEXT,          -- optional: what the user wishes the answer was
            note TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_iact ON interactions(interaction_id);
        CREATE INDEX IF NOT EXISTS idx_fb ON feedback(interaction_id);
        """)
        self.conn.commit()

    # ─────────────────── writes ───────────────────
    def log_interaction(
        self,
        interaction_id: str,
        question: str,
        corrected_query: str,
        answer: str,
        citations: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        subject: Optional[str] = None,
        book: Optional[str] = None,
        chapter: Optional[str] = None,
    ) -> int:
        cur = self.conn.cursor()
        cur.execute(
            """INSERT INTO interactions
               (ts, interaction_id, user_id, question, corrected_query, answer,
                citations_json, subject, book, chapter)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                time.time(),
                interaction_id,
                user_id,
                question,
                corrected_query,
                answer,
                json.dumps(citations[:10]),
                subject,
                book,
                chapter,
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def log_feedback(
        self,
        interaction_id: str,
        rating: int,
        corrected_answer: Optional[str] = None,
        note: Optional[str] = None,
    ) -> int:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO feedback (ts, interaction_id, rating, corrected_answer, note) VALUES (?, ?, ?, ?, ?)",
            (time.time(), interaction_id, int(rating), corrected_answer, note),
        )
        self.conn.commit()
        return cur.lastrowid

    # ─────────────────── reads ───────────────────
    def stats(self) -> Dict[str, int]:
        cur = self.conn.cursor()
        rows = cur.execute(
            "SELECT (SELECT COUNT(*) FROM interactions), "
            "(SELECT COUNT(*) FROM feedback WHERE rating > 0), "
            "(SELECT COUNT(*) FROM feedback WHERE rating < 0)"
        ).fetchone()
        return {
            "interactions": int(rows[0]),
            "positive": int(rows[1]),
            "negative": int(rows[2]),
        }

    def export_jsonl(self, only_rated: bool = True) -> List[Dict[str, Any]]:
        """Return training examples in instruction/response form."""
        cur = self.conn.cursor()
        if only_rated:
            sql = """
              SELECT i.question, i.corrected_query, i.answer, i.citations_json,
                     f.rating, f.corrected_answer
              FROM interactions i
              JOIN feedback f ON f.interaction_id = i.interaction_id
            """
        else:
            sql = """
              SELECT i.question, i.corrected_query, i.answer, i.citations_json,
                     COALESCE((SELECT MAX(rating) FROM feedback f WHERE f.interaction_id = i.interaction_id), 0) AS rating,
                     (SELECT corrected_answer FROM feedback f WHERE f.interaction_id = i.interaction_id ORDER BY ts DESC LIMIT 1) AS corrected_answer
              FROM interactions i
            """
        rows = cur.execute(sql).fetchall()
        out: List[Dict[str, Any]] = []
        for q, cq, a, cj, rating, corr in rows:
            citations = json.loads(cj or "[]")
            target = corr if (rating < 0 and corr) else a
            label = "preferred" if (rating > 0 or (rating < 0 and corr)) else "rejected"
            out.append({
                "instruction": q,
                "rewritten_query": cq,
                "context_titles": [c.get("chapter") for c in citations[:5]],
                "response": target,
                "label": label,
                "rating": rating,
            })
        return out


_store_singleton: Optional[FeedbackStore] = None


def get_feedback_store() -> FeedbackStore:
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = FeedbackStore()
        logger.info("FeedbackStore opened: {}", _store_singleton.db_path)
    return _store_singleton
