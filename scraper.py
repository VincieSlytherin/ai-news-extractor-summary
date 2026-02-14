import asyncio
import logging
import re
from datetime import datetime, timedelta

import feedparser
import httpx
from bs4 import BeautifulSoup

from storage import Article

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "AI-News-Aggregator/1.0 (Personal Use)"
}

AI_KEYWORDS = re.compile(
    r"\b(ai|artificial.intelligence|machine.learning|deep.learning|llm|gpt|"
    r"neural.network|transformer|diffusion|generative|nlp|computer.vision|"
    r"reinforcement.learning|foundation.model|rag|fine.?tun|prompt|embedding|"
    r"langchain|openai|anthropic|gemini|mistral|llama|claude|"
    r"agent|agentic|multi.?agent|tool.?use|function.?call|mcp|a2a)\b",
    re.IGNORECASE,
)


async def scrape_all(sites: list[dict]) -> list[Article]:
    """Scrape all configured sites concurrently and return a flat list of articles."""
    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        tasks = []
        for site in sites:
            site_type = site["type"]
            if site_type == "rss":
                tasks.append(_scrape_rss(client, site))
            elif site_type == "api":
                tasks.append(_scrape_hn(client, site))
            elif site_type == "web":
                tasks.append(_scrape_web(client, site))
            else:
                logger.warning(f"Unknown site type: {site_type} for {site['name']}")

        results = await asyncio.gather(*tasks, return_exceptions=True)

    articles = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Failed to scrape {sites[i]['name']}: {result}")
        else:
            articles.extend(result)
            logger.info(f"Scraped {len(result)} articles from {sites[i]['name']}")

    return articles


async def _scrape_rss(client: httpx.AsyncClient, site: dict) -> list[Article]:
    """Parse an RSS/Atom feed and return recent articles (last 3 days)."""
    resp = await client.get(site["url"])
    resp.raise_for_status()

    feed = feedparser.parse(resp.text)
    cutoff = datetime.now() - timedelta(days=3)
    articles = []

    for entry in feed.entries[:30]:  # Limit to most recent 30 entries
        published = _parse_date(entry)
        if published and published < cutoff:
            continue

        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue

        # Extract content: prefer summary, then content
        content = ""
        if hasattr(entry, "summary"):
            content = _clean_html(entry.summary)
        elif hasattr(entry, "content"):
            content = _clean_html(entry.content[0].get("value", ""))

        # Truncate long content to save tokens
        if len(content) > 1500:
            content = content[:1500] + "..."

        articles.append(Article(
            title=title,
            url=link,
            content=content,
            source=site["name"],
            category=site.get("category", ""),
            date=published.isoformat() if published else datetime.now().isoformat(),
        ))

    return articles


async def _scrape_hn(client: httpx.AsyncClient, site: dict) -> list[Article]:
    """Fetch top Hacker News stories and filter for AI-related content."""
    base_url = site["url"]
    resp = await client.get(f"{base_url}/topstories.json")
    resp.raise_for_status()
    story_ids = resp.json()[:60]  # Check top 60 stories

    articles = []
    # Fetch stories in batches of 10 to avoid overwhelming the API
    for batch_start in range(0, len(story_ids), 10):
        batch = story_ids[batch_start:batch_start + 10]
        tasks = [client.get(f"{base_url}/item/{sid}.json") for sid in batch]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for r in responses:
            if isinstance(r, Exception):
                continue
            story = r.json()
            if not story:
                continue

            title = story.get("title", "")
            url = story.get("url", "")
            if not url:
                url = f"https://news.ycombinator.com/item?id={story.get('id', '')}"

            # Filter for AI-related stories
            text_to_check = f"{title} {story.get('text', '')}"
            if not AI_KEYWORDS.search(text_to_check):
                continue

            score = story.get("score", 0)
            descendants = story.get("descendants", 0)
            content = f"Score: {score} | Comments: {descendants}"
            if story.get("text"):
                content += f"\n{_clean_html(story['text'][:1000])}"

            ts = story.get("time", 0)
            date = datetime.fromtimestamp(ts) if ts else datetime.now()

            articles.append(Article(
                title=title,
                url=url,
                content=content,
                source="Hacker News",
                category=site.get("category", "news"),
                date=date.isoformat(),
            ))

        # Rate limiting between batches
        await asyncio.sleep(0.5)

    return articles


async def _scrape_web(client: httpx.AsyncClient, site: dict) -> list[Article]:
    """Scrape a website by extracting article elements with CSS selectors."""
    try:
        resp = await client.get(site["url"])
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning(f"HTTP error scraping {site['name']}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    selector = site.get("selector", "article")
    articles = []

    # Try to find article elements
    elements = soup.select(selector)
    if not elements:
        # Fallback: look for common article patterns
        elements = soup.select("a[href]")

    for elem in elements[:20]:
        # Extract title and link
        link_tag = elem if elem.name == "a" else elem.select_one("a[href]")
        if not link_tag:
            continue

        href = link_tag.get("href", "").strip()
        if not href or href == "#":
            continue

        # Make absolute URL
        if href.startswith("/"):
            from urllib.parse import urljoin
            href = urljoin(site["url"], href)

        # Extract title
        title_tag = elem.select_one("h1, h2, h3, h4, .title")
        title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        # Extract snippet
        snippet_tag = elem.select_one("p, .summary, .desc, .description, .excerpt")
        content = snippet_tag.get_text(strip=True) if snippet_tag else ""

        articles.append(Article(
            title=title[:200],
            url=href,
            content=content[:1000],
            source=site["name"],
            category=site.get("category", "chinese"),
            date=datetime.now().isoformat(),
        ))

    return articles


def _clean_html(html: str) -> str:
    """Strip HTML tags and return plain text."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def _parse_date(entry) -> "datetime | None":
    """Try to parse a date from a feed entry."""
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                from time import mktime
                return datetime.fromtimestamp(mktime(parsed))
            except (ValueError, OverflowError):
                pass
    return None
