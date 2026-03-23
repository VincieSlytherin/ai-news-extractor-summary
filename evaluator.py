"""LLM-as-judge evaluation for summarization quality.

For each article, scores the AI-generated summary on two dimensions:
  - faithfulness (0-10): accuracy relative to source, no hallucinations
  - coverage    (0-10): how well the summary covers the main points

Uses gpt-4o-mini by default (~$0.003/day for 50 articles). Results are
stored in SQLite and surfaced as a quality trend chart in the dashboard.
"""
from __future__ import annotations

import json
import logging

from openai import OpenAI

from storage import Article

logger = logging.getLogger(__name__)

_EVAL_PROMPT = """\
You are evaluating an AI-generated summary of a news article.

Article content (may be truncated):
{content}

Generated summary:
{summary}

Score on two dimensions from 0 to 10:
- faithfulness: Does the summary accurately reflect the article without adding false information? (10 = perfectly faithful)
- coverage: Does the summary cover the article's main points? (10 = comprehensive)

Reply in JSON only, no other text:
{{"faithfulness": <int 0-10>, "coverage": <int 0-10>, "note": "<one sentence reason>"}}"""


def evaluate_summary(content: str, summary: str, openai_config: dict) -> dict:
    """Score a single summary. Returns {"faithfulness", "coverage", "note"}."""
    if not content or not summary:
        return {"faithfulness": 0, "coverage": 0, "note": "missing input"}

    client = OpenAI(api_key=openai_config.get("api_key", ""))
    # Always use a fast cheap model for evaluation — not the digest model
    model = openai_config.get("eval_model", "gpt-4o-mini")

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": _EVAL_PROMPT.format(
                    content=content[:2000],
                    summary=summary[:1000],
                ),
            }],
            max_tokens=120,
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        return {
            "faithfulness": max(0, min(10, int(data.get("faithfulness", 0)))),
            "coverage": max(0, min(10, int(data.get("coverage", 0)))),
            "note": str(data.get("note", "")),
        }
    except Exception as e:
        logger.error("Evaluation API error: %s", e)
        return {"faithfulness": 0, "coverage": 0, "note": f"error: {e}"}


def evaluate_batch(
    articles: list[Article],
    summaries: dict[str, str],
    openai_config: dict,
) -> dict[str, dict]:
    """Evaluate all articles that have a non-empty summary.

    Returns a dict mapping article URL to its score dict.
    """
    results: dict[str, dict] = {}
    to_eval = [(a, summaries[a.url]) for a in articles if summaries.get(a.url)]

    logger.info("Evaluating %d article summaries...", len(to_eval))
    for i, (article, summary) in enumerate(to_eval, 1):
        results[article.url] = evaluate_summary(article.content, summary, openai_config)
        if i % 10 == 0:
            logger.info("  evaluated %d / %d", i, len(to_eval))

    avg_f = sum(r["faithfulness"] for r in results.values()) / len(results) if results else 0
    avg_c = sum(r["coverage"] for r in results.values()) / len(results) if results else 0
    logger.info(
        "Evaluation complete — avg faithfulness %.1f, avg coverage %.1f",
        avg_f, avg_c,
    )
    return results
