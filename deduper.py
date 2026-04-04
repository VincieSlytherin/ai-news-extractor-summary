"""Semantic deduplication using OpenAI embeddings and cosine similarity.

Flow:
  1. Get embeddings for all new articles (title + content snippet).
  2. Compare against embeddings of articles saved in the last N days.
  3. Drop any new article whose similarity to a stored/kept article >= threshold.
  4. Return the surviving articles and their embeddings (for storage).
"""
from __future__ import annotations

import logging

import numpy as np
from openai import OpenAI

from storage import Article

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_THRESHOLD = 0.90  # tune down to catch more near-dups, up to be stricter


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom else 0.0


def _batch_embeddings(texts: list[str], client: OpenAI) -> list[list[float]]:
    """Fetch embeddings in batches of 100 (API limit)."""
    results: list[list[float]] = []
    for i in range(0, len(texts), 100):
        batch = texts[i : i + 100]
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        ordered = sorted(resp.data, key=lambda d: d.index)
        results.extend(d.embedding for d in ordered)
    return results


def filter_semantic_duplicates(
    articles: list[Article],
    stored_embeddings: list[tuple[str, list[float]]],
    openai_config: dict,
    threshold: float = DEFAULT_THRESHOLD,
) -> tuple[list[Article], dict[str, list[float]]]:
    """Filter near-duplicate articles using embedding similarity.

    Args:
        articles: Candidate new articles (already URL-deduped).
        stored_embeddings: (url, embedding) pairs from recent DB records.
        openai_config: Dict with 'api_key' key.
        threshold: Cosine similarity cutoff (0-1). Higher = stricter.

    Returns:
        (kept_articles, new_embeddings) where new_embeddings maps url -> vector.
    """
    if not articles:
        return [], {}

    client = OpenAI(api_key=openai_config.get("api_key", ""))
    texts = [f"{a.title}\n{a.content[:500]}" for a in articles]

    try:
        new_vecs = _batch_embeddings(texts, client)
    except Exception as e:
        logger.error("Embedding API error during semantic dedup, skipping: %s", e)
        return articles, {}  # fail open: keep all articles

    # Seed the seen pool with already-stored embeddings
    seen: list[list[float]] = [emb for _, emb in stored_embeddings]

    kept_articles: list[Article] = []
    kept_embeddings: dict[str, list[float]] = {}

    for article, vec in zip(articles, new_vecs):
        is_dup = any(_cosine_similarity(vec, s) >= threshold for s in seen)
        if is_dup:
            logger.info("Semantic duplicate dropped: %.60s", article.title)
            continue
        kept_articles.append(article)
        kept_embeddings[article.url] = vec
        seen.append(vec)  # prevent intra-batch duplicates too

    logger.info(
        "Semantic dedup: %d -> %d articles (dropped %d near-duplicates)",
        len(articles), len(kept_articles), len(articles) - len(kept_articles),
    )
    return kept_articles, kept_embeddings
