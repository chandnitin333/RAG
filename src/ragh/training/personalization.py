"""Personalization engine: per-user topic stats + insights.

We track each interaction's (user_id, subject, chapter, agent, rating) so we
can compute weak-topic insights and recommend study plans.
"""
from typing import List, Dict, Any, Optional
from pathlib import Path
import sqlite3
import time
from loguru import logger

from ragh.config import settings


class PersonalizationStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or (settings.INDEX_DIR / "personalization.sqlite"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._init()

    def _init(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            user_id TEXT NOT NULL,
            subject TEXT,
            book TEXT,
            chapter TEXT,
            agent TEXT,
            question TEXT,
            corrected TEXT,
            interaction_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_user ON history(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_subject ON history(user_id, subject);
        """)
        self.conn.commit()

    def log(self, **kw):
        cols = ["ts", "user_id", "subject", "book", "chapter", "agent",
                "question", "corrected", "interaction_id"]
        kw["ts"] = time.time()
        kw.setdefault("user_id", "anonymous")
        values = [kw.get(c) for c in cols]
        placeholders = ",".join(["?"] * len(cols))
        self.conn.execute(
            f"INSERT INTO history ({','.join(cols)}) VALUES ({placeholders})",
            values,
        )
        self.conn.commit()

    def insights(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        cutoff = time.time() - days * 86400
        cur = self.conn.cursor()
        rows = cur.execute(
            "SELECT subject, chapter, agent FROM history WHERE user_id = ? AND ts >= ?",
            (user_id, cutoff),
        ).fetchall()
        total = len(rows)
        by_subject: Dict[str, int] = {}
        by_chapter: Dict[str, int] = {}
        by_agent: Dict[str, int] = {}
        for s, c, a in rows:
            if s: by_subject[s] = by_subject.get(s, 0) + 1
            if c: by_chapter[c] = by_chapter.get(c, 0) + 1
            if a: by_agent[a] = by_agent.get(a, 0) + 1

        # weak-topics heuristic: chapters with >=3 questions are flagged as
        # current focus areas (likely something the user is struggling with).
        weak = sorted(
            [(c, n) for c, n in by_chapter.items() if n >= 3],
            key=lambda x: -x[1],
        )

        # build a simple study suggestion
        recommendations = []
        for chapter, hits in weak[:5]:
            subj = next(
                (s for s, c, _ in rows if c == chapter and s), None
            ) or "Unknown"
            recommendations.append({
                "subject": subj,
                "chapter": chapter,
                "rationale": f"You asked {hits} questions on this — practice 3 numericals + revise key formulas.",
            })

        recent = cur.execute(
            "SELECT corrected, agent, ts FROM history WHERE user_id = ? ORDER BY ts DESC LIMIT 10",
            (user_id,),
        ).fetchall()

        return {
            "user_id": user_id,
            "window_days": days,
            "total_questions": total,
            "by_subject": by_subject,
            "by_agent": by_agent,
            "top_chapters": dict(weak[:10]),
            "recommendations": recommendations,
            "recent": [
                {"query": r[0], "agent": r[1], "ts": r[2]} for r in recent
            ],
        }


_singleton: Optional[PersonalizationStore] = None


def get_personalization_store() -> PersonalizationStore:
    global _singleton
    if _singleton is None:
        _singleton = PersonalizationStore()
        logger.info("PersonalizationStore opened: {}", _singleton.db_path)
    return _singleton
