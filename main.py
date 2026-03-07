#!/usr/bin/env python3
"""AI News Aggregator - Daily digest of AI/ML news from multiple sources."""

import argparse
import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from deduper import filter_semantic_duplicates
from emailer import send_email
from scraper import enrich_with_full_content, scrape_all
from storage import Storage
from summarizer import summarize, summarize_articles

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(DATA_DIR / "run.log"),
    ],
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load config from YAML file and resolve environment variables."""
    load_dotenv(PROJECT_DIR / ".env")

    config_path = PROJECT_DIR / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    config.setdefault("openai", {})
    config["openai"]["api_key"] = os.environ.get("OPENAI_API_KEY", "")

    config.setdefault("email", {})
    config["email"]["sender"] = os.environ.get("EMAIL_SENDER", "")
    config["email"]["recipient"] = os.environ.get("EMAIL_RECIPIENT", "")
    config["email"]["password"] = os.environ.get("EMAIL_PASSWORD", "")

    return config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI News Aggregator")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print digest to console without sending email",
    )
    parser.add_argument(
        "--no-semantic-dedup",
        action="store_true",
        help="Skip semantic deduplication (saves embedding API tokens)",
    )
    return parser.parse_args()


async def run(dry_run: bool = False, semantic_dedup: bool = True):
    config = load_config()
    db = Storage(str(DATA_DIR / "news.db"))
    run_id = db.start_run()
    today = datetime.now().strftime("%Y-%m-%d")

    try:
        # 1. Scrape all sites
        logger.info("Starting scrape of %d sites...", len(config["sites"]))
        articles = await scrape_all(config["sites"])
        logger.info("Scraped %d total articles", len(articles))

        # 2. URL deduplication
        new_articles = db.filter_new(articles)
        logger.info("Found %d new articles after URL dedup", len(new_articles))

        if not new_articles:
            logger.info("No new articles. Done.")
            db.finish_run(run_id, "success", scraped=len(articles), new_articles=0)
            return

        # 3. Semantic deduplication (drops near-duplicate cross-source stories)
        article_embeddings: dict = {}
        if semantic_dedup:
            logger.info("Running semantic deduplication...")
            stored_embs = db.get_recent_embeddings(days=7)
            new_articles, article_embeddings = filter_semantic_duplicates(
                new_articles, stored_embs, config["openai"]
            )
            if not new_articles:
                logger.info("All articles were semantic duplicates. Done.")
                db.finish_run(run_id, "success", scraped=len(articles), new_articles=0)
                return

        # 4. Fetch full article content (replaces RSS snippets with full text)
        logger.info("Fetching full article content for %d articles...", len(new_articles))
        new_articles = await enrich_with_full_content(new_articles)

        # 5. Per-article AI summaries
        logger.info("Generating per-article summaries for %d articles...", len(new_articles))
        article_summaries = summarize_articles(new_articles, config["openai"])

        # 6. Overall digest
        logger.info("Generating AI digest...")
        summary = summarize(new_articles, config["openai"], article_summaries)
        logger.info("Digest generated (%d chars)", len(summary))

        # 7. Deliver: email or console
        if dry_run:
            print("\n" + "=" * 60)
            print(summary)
            print("=" * 60)
        else:
            email_cfg = config.get("email", {})
            if email_cfg.get("password"):
                logger.info("Sending email digest...")
                send_email(summary, email_cfg)
            else:
                logger.warning("EMAIL_PASSWORD not set. Printing to console instead.")
                print("\n" + "=" * 60)
                print(summary)
                print("=" * 60)

        # 8. Persist to DB
        db.save(new_articles, summaries=article_summaries, embeddings=article_embeddings)
        db.save_digest(today, summary, article_count=len(new_articles))
        logger.info("Saved %d articles and digest to database", len(new_articles))

        # 9. Cleanup records older than 30 days
        db.cleanup(days=30)

        db.finish_run(
            run_id, "success",
            scraped=len(articles),
            new_articles=len(new_articles),
        )

    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        db.finish_run(run_id, "error", error=str(e))
        raise
    finally:
        db.close()


def main():
    args = parse_args()
    asyncio.run(run(dry_run=args.dry_run, semantic_dedup=not args.no_semantic_dedup))


if __name__ == "__main__":
    main()
