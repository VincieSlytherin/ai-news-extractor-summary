import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


@dataclass
class Article:
    title: str
    url: str
    content: str
    source: str
    category: str
    date: str  # ISO format string


class Storage:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT,
                summary TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self.conn.commit()

    def filter_new(self, articles: list[Article]) -> list[Article]:
        """Return only articles whose URLs are not already in the database."""
        if not articles:
            return []
        existing = set()
        cursor = self.conn.execute("SELECT url FROM articles")
        for row in cursor:
            existing.add(row[0])
        return [a for a in articles if a.url not in existing]

    def save(self, articles: list[Article], summaries: Optional[dict] = None):
        """Save articles to the database. Optionally attach per-article summaries."""
        summaries = summaries or {}
        for a in articles:
            try:
                self.conn.execute(
                    "INSERT OR IGNORE INTO articles (url, title, source, category, content, summary, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (a.url, a.title, a.source, a.category, a.content,
                     summaries.get(a.url, ""), a.date or datetime.now().isoformat()),
                )
            except sqlite3.IntegrityError:
                pass
        self.conn.commit()

    def cleanup(self, days: int = 30):
        """Remove articles older than the specified number of days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        self.conn.execute("DELETE FROM articles WHERE created_at < ?", (cutoff,))
        self.conn.commit()

    def close(self):
        self.conn.close()
