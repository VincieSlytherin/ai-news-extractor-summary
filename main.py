#!/usr/bin/env python3
"""AI News Aggregator - Daily digest of AI/ML news from multiple sources."""

import argparse
import asyncio
import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from emailer import send_email
from scraper import scrape_all
from storage import Storage
from summarizer import summarize, summarize_articles

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"

# Ensure data directory exists before setting up file logging
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

    # Resolve secrets from environment
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
    return parser.parse_args()


async def run(dry_run: bool = False):
    config = load_config()
    db = Storage(str(DATA_DIR / "news.db"))

    try:
        # 1. Scrape all sites
        logger.info("Starting scrape of %d sites...", len(config["sites"]))
        articles = await scrape_all(config["sites"])
        logger.info("Scraped %d total articles", len(articles))

        # 2. Filter out already-seen articles
        new_articles = db.filter_new(articles)
        logger.info("Found %d new articles", len(new_articles))

        if not new_articles:
            logger.info("No new articles. Done.")
            return

        # 3. Generate per-article detailed summaries
        logger.info("Generating per-article summaries for %d articles...", len(new_articles))
        article_summaries = summarize_articles(new_articles, config["openai"])
        logger.info("Per-article summaries generated (%d articles)", len(article_summaries))

        # 4. Generate overall AI digest (enriched with per-article summaries)
        logger.info("Generating AI digest...")
        summary = summarize(new_articles, config["openai"], article_summaries)
        logger.info("Digest generated (%d chars)", len(summary))

        # 5. Send email or print
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

        # 6. Save articles to DB for deduplication (with per-article summaries)
        db.save(new_articles, summaries=article_summaries)
        logger.info("Saved %d articles to database", len(new_articles))

        # 7. Cleanup old records
        db.cleanup(days=30)

    finally:
        db.close()


def main():
    args = parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
