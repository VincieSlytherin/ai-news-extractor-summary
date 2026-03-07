import json
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
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
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
                embedding TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Migration: add embedding column if upgrading from older schema
        try:
            self.conn.execute("ALTER TABLE articles ADD COLUMN embedding TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS digests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                markdown TEXT NOT NULL,
                article_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                articles_scraped INTEGER DEFAULT 0,
                articles_new INTEGER DEFAULT 0,
                error TEXT
            )
        """)
        self.conn.commit()

    def filter_new(self, articles: list[Article]) -> list[Article]:
        """Return only articles whose URLs are not already in the database."""
        if not articles:
            return []
        cursor = self.conn.execute("SELECT url FROM articles")
        existing = {row[0] for row in cursor}
        return [a for a in articles if a.url not in existing]

    def save(
        self,
        articles: list[Article],
        summaries: Optional[dict] = None,
        embeddings: Optional[dict] = None,
    ):
        """Save articles to the database with optional summaries and embeddings."""
        summaries = summaries or {}
        embeddings = embeddings or {}
        for a in articles:
            emb = embeddings.get(a.url)
            try:
                self.conn.execute(
                    "INSERT OR IGNORE INTO articles "
                    "(url, title, source, category, content, summary, embedding, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        a.url, a.title, a.source, a.category, a.content,
                        summaries.get(a.url, ""),
                        json.dumps(emb) if emb else None,
                        a.date or datetime.now().isoformat(),
                    ),
                )
            except sqlite3.IntegrityError:
                pass
        self.conn.commit()

    def get_recent_embeddings(self, days: int = 7) -> list[tuple[str, list]]:
        """Return (url, embedding) pairs for articles saved in the last N days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor = self.conn.execute(
            "SELECT url, embedding FROM articles WHERE embedding IS NOT NULL AND created_at >= ?",
            (cutoff,),
        )
        result = []
        for url, emb_json in cursor.fetchall():
            try:
                result.append((url, json.loads(emb_json)))
            except Exception:
                pass
        return result

    def cleanup(self, days: int = 30):
        """Remove articles older than the specified number of days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        self.conn.execute("DELETE FROM articles WHERE created_at < ?", (cutoff,))
        self.conn.commit()

    # --- Digests ---

    def save_digest(self, date: str, markdown: str, article_count: int):
        self.conn.execute(
            "INSERT INTO digests (date, markdown, article_count) VALUES (?, ?, ?)",
            (date, markdown, article_count),
        )
        self.conn.commit()

    def get_digests(self, limit: int = 30) -> list[dict]:
        cursor = self.conn.execute(
            "SELECT id, date, markdown, article_count, created_at "
            "FROM digests ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    # --- Articles (for dashboard) ---

    def get_articles(
        self, limit: int = 200, search: str = "", category: str = ""
    ) -> list[dict]:
        query = (
            "SELECT id, url, title, source, category, summary, created_at "
            "FROM articles WHERE 1=1"
        )
        params: list = []
        if search:
            query += " AND (title LIKE ? OR summary LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cursor = self.conn.execute(query, params)
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    # --- Run tracking ---

    def start_run(self) -> int:
        cursor = self.conn.execute(
            "INSERT INTO runs (started_at) VALUES (?)",
            (datetime.now().isoformat(),),
        )
        self.conn.commit()
        return cursor.lastrowid

    def finish_run(
        self,
        run_id: int,
        status: str,
        scraped: int = 0,
        new_articles: int = 0,
        error: str = "",
    ):
        self.conn.execute(
            "UPDATE runs SET finished_at=?, status=?, articles_scraped=?, articles_new=?, error=? "
            "WHERE id=?",
            (
                datetime.now().isoformat(), status, scraped, new_articles,
                error or None, run_id,
            ),
        )
        self.conn.commit()

    def get_runs(self, limit: int = 20) -> list[dict]:
        cursor = self.conn.execute(
            "SELECT id, started_at, finished_at, status, articles_scraped, articles_new, error "
            "FROM runs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        )
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def close(self):
        self.conn.close()
