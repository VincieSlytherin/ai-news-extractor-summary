"""FastAPI service layer for AI News Aggregator.

Exposes the SQLite data as a REST API so any frontend (or external client)
can consume digests, articles, quality metrics, and run history.

Run:  uvicorn api:app --host 0.0.0.0 --port 8000 --reload
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from storage import Storage

DATA_DIR = Path(__file__).parent / "data"
app = FastAPI(title="AI News Aggregator API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _db() -> Storage:
    return Storage(str(DATA_DIR / "news.db"))


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@app.get("/api/stats")
def get_stats():
    """Overview metrics: article counts, source/category breakdown, last run."""
    db = _db()
    try:
        articles = db.get_articles(limit=10_000)
        digests = db.get_digests(limit=1_000)
        runs = db.get_runs(limit=1)
        return {
            "total_articles": len(articles),
            "total_digests": len(digests),
            "last_run": runs[0] if runs else None,
            "articles_by_source": dict(
                sorted(Counter(a["source"] for a in articles).items(), key=lambda x: x[1], reverse=True)
            ),
            "articles_by_category": dict(Counter(a["category"] for a in articles)),
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Digests
# ---------------------------------------------------------------------------

@app.get("/api/digests")
def list_digests(limit: int = Query(30, le=100)):
    """List recent digests (metadata only, no markdown body)."""
    db = _db()
    try:
        digests = db.get_digests(limit=limit)
        # Strip markdown to keep response small
        return [
            {k: v for k, v in d.items() if k != "markdown"}
            for d in digests
        ]
    finally:
        db.close()


@app.get("/api/digest/{date}")
def get_digest(date: str):
    """Retrieve a full digest by date (YYYY-MM-DD)."""
    db = _db()
    try:
        digests = db.get_digests(limit=365)
        for d in digests:
            if d["date"] == date:
                return d
        raise HTTPException(status_code=404, detail=f"No digest found for {date}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------

@app.get("/api/articles")
def list_articles(
    limit: int = Query(100, le=500),
    search: str = Query("", description="Keyword search across title and summary"),
    category: str = Query("", description="Filter by category"),
):
    """List articles with optional keyword search and category filter."""
    db = _db()
    try:
        return db.get_articles(limit=limit, search=search, category=category)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Quality / Evaluation
# ---------------------------------------------------------------------------

@app.get("/api/quality/trend")
def get_quality_trend(days: int = Query(30, le=90)):
    """Daily average faithfulness and coverage scores over the last N days."""
    db = _db()
    try:
        return db.get_quality_trend(days=days)
    finally:
        db.close()


@app.get("/api/quality/evaluations")
def get_evaluations(limit: int = Query(100, le=500)):
    """Individual per-article evaluation scores."""
    db = _db()
    try:
        return db.get_evaluations(limit=limit)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

@app.get("/api/runs")
def list_runs(limit: int = Query(20, le=100)):
    """Pipeline run history with status, counts, and errors."""
    db = _db()
    try:
        return db.get_runs(limit=limit)
    finally:
        db.close()
