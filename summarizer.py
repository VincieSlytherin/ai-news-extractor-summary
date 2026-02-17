from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from openai import OpenAI

from storage import Article

logger = logging.getLogger(__name__)

# GPT-5+ models require max_completion_tokens instead of max_tokens
_NEW_TOKEN_PARAM_MODELS = ("gpt-5", "o1", "o3")


def _token_limit_param(model: str, max_tokens: int) -> dict:
    """Return the correct token-limit kwarg for the given model."""
    if any(model.startswith(prefix) for prefix in _NEW_TOKEN_PARAM_MODELS):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens}

SYSTEM_PROMPT = """You are an AI news digest curator. Create a bilingual (Chinese + English) daily digest
of AI/ML/Agent news and blog posts for a technical reader.

Format Rules:
- Group articles by theme (e.g., "LLM Advances / LLM 进展", "Industry News / 行业动态",
  "Research Papers / 研究论文", "Engineering Practices / 工程实践", "Agent & Tools / Agent 与工具")
- Start with "Today's Highlights / 今日亮点" — pick the 3-5 most important articles
- For EACH article, provide:
  1. Title (original language)
  2. Chinese summary: 1-2 sentence summary in Chinese
  3. English summary: 1-2 sentence summary in English
  4. Key takeaway / 关键要点: one bilingual sentence
  5. Source and link: [Source](original_url)
- Every article MUST include its original URL as a clickable Markdown link
- You MUST cover ALL articles provided — do not skip any article
- Output in clean Markdown format"""

ARTICLE_SUMMARY_SYSTEM_PROMPT = """You are a senior AI/ML technical analyst. For each article provided,
write a detailed and specific summary (摘要) in both Chinese and English.

Requirements for each article summary:
- 3-5 sentences covering: what the article is about, key technical details, main findings or announcements, and why it matters
- Be SPECIFIC — include names, numbers, model names, benchmarks, companies, etc.
- Chinese summary (中文摘要): Detailed, natural Chinese
- English summary (English Abstract): Detailed, professional English
- Output format: Use the exact format below for EACH article

Format:
### [Article Number]. {Title}
**来源 / Source**: {source}
**链接 / Link**: {url}

**中文摘要**:
{3-5 sentence detailed Chinese summary}

**English Abstract**:
{3-5 sentence detailed English summary}

---"""

ARTICLE_SUMMARY_USER_TEMPLATE = """Please generate a detailed summary (摘要) for each of the following {count} articles.
Be specific and technical — include key details, numbers, and names mentioned in the articles.

{articles_text}"""

USER_PROMPT_TEMPLATE = """Here are today's ({date}) collected AI/ML/Agent articles.
Please create a bilingual (中英双语) structured daily digest. Each article must have both Chinese and English summaries with the original link.

{articles_text}"""


def summarize_articles(articles: list[Article], openai_config: dict) -> dict[str, str]:
    """Generate a detailed per-article summary for each article using OpenAI API.

    Returns a dict mapping article URL to its detailed summary text.
    """
    if not articles:
        return {}

    api_key = openai_config.get("api_key", "")
    model = openai_config.get("model", "gpt-4o-mini")

    client = OpenAI(api_key=api_key)
    summaries: dict[str, str] = {}

    # Process in batches of 10 to stay within token limits
    batch_size = 10
    for i in range(0, len(articles), batch_size):
        batch = articles[i : i + batch_size]
        articles_text = _format_articles(batch)

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": ARTICLE_SUMMARY_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": ARTICLE_SUMMARY_USER_TEMPLATE.format(
                            count=len(batch), articles_text=articles_text
                        ),
                    },
                ],
                **_token_limit_param(model, 8000),
                temperature=0.3,
            )
            batch_result = response.choices[0].message.content

            # Map the full batch summary text back to each article URL
            # Split by article sections and match
            sections = batch_result.split("---")
            for j, article in enumerate(batch):
                if j < len(sections):
                    summaries[article.url] = sections[j].strip()
                else:
                    summaries[article.url] = ""

            logger.info(
                "Generated summaries for articles %d-%d of %d",
                i + 1, min(i + batch_size, len(articles)), len(articles),
            )
        except Exception as e:
            logger.error(f"Per-article summary error (batch {i // batch_size + 1}): {e}")
            for article in batch:
                summaries[article.url] = ""

    return summaries


def summarize(
    articles: list[Article],
    openai_config: dict,
    article_summaries: dict[str, str] | None = None,
) -> str:
    """Generate a structured digest of articles using OpenAI API.

    If article_summaries is provided, they are included in the prompt to produce
    a richer digest. The per-article summaries section is also appended to the
    final output so readers can see every article's detailed abstract.
    """
    if not articles:
        return "No new articles today."

    api_key = openai_config.get("api_key", "")
    model = openai_config.get("model", "gpt-4o-mini")
    max_tokens = openai_config.get("max_tokens", 4000)

    client = OpenAI(api_key=api_key)

    # Format articles for the prompt, enriched with per-article summaries
    articles_text = _format_articles(articles, article_summaries)

    # If content is very long, split into batches
    if len(articles_text) > 30000:
        digest = _summarize_in_batches(client, model, max_tokens, articles, article_summaries)
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        user_prompt = USER_PROMPT_TEMPLATE.format(date=today, articles_text=articles_text)

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                **_token_limit_param(model, max_tokens),
                temperature=0.3,
            )
            digest = response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            digest = _fallback_summary(articles)

    # Append detailed per-article summaries section
    if article_summaries:
        digest += _build_article_summaries_section(articles, article_summaries)

    return digest


def _summarize_in_batches(
    client: OpenAI,
    model: str,
    max_tokens: int,
    articles: list[Article],
    article_summaries: dict[str, str] | None = None,
) -> str:
    """Split articles into batches and summarize each, then merge."""
    batch_size = 15
    partial_summaries = []

    for i in range(0, len(articles), batch_size):
        batch = articles[i : i + batch_size]
        articles_text = _format_articles(batch, article_summaries)
        today = datetime.now().strftime("%Y-%m-%d")

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": USER_PROMPT_TEMPLATE.format(
                            date=today, articles_text=articles_text
                        ),
                    },
                ],
                **_token_limit_param(model, max_tokens),
                temperature=0.3,
            )
            partial_summaries.append(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Batch summarization error: {e}")
            partial_summaries.append(_fallback_summary(batch))

    # Merge partial summaries
    if len(partial_summaries) == 1:
        return partial_summaries[0]

    try:
        merge_prompt = (
            "Below are partial daily digest sections. "
            "Merge them into a single cohesive daily digest, "
            "removing duplicates and re-organizing by theme. "
            "Keep the same format.\n\n"
            + "\n---\n".join(partial_summaries)
        )
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": merge_prompt},
            ],
            **_token_limit_param(model, max_tokens),
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Merge summarization error: {e}")
        return "\n\n---\n\n".join(partial_summaries)


def _format_articles(
    articles: list[Article], article_summaries: dict[str, str] | None = None
) -> str:
    """Format articles into a text block for the prompt.

    When per-article summaries are available, they are appended to each article
    so the digest LLM can leverage them for a richer output.
    """
    summaries = article_summaries or {}
    parts = []
    for i, a in enumerate(articles, 1):
        block = (
            f"[{i}] **{a.title}**\n"
            f"Source: {a.source} | Category: {a.category}\n"
            f"URL: {a.url}\n"
            f"Content: {a.content}\n"
        )
        summary = summaries.get(a.url, "")
        if summary:
            block += f"Detailed Summary: {summary}\n"
        parts.append(block)
    return "\n".join(parts)


def _build_article_summaries_section(
    articles: list[Article], article_summaries: dict[str, str]
) -> str:
    """Build the per-article detailed summaries appendix for the final digest."""
    lines = [
        "\n\n---\n",
        "# 每篇文章详细摘要 / Detailed Article Summaries\n",
    ]
    for i, a in enumerate(articles, 1):
        summary = article_summaries.get(a.url, "")
        if not summary:
            continue
        lines.append(f"\n{summary}\n")
    return "\n".join(lines)


def _fallback_summary(articles: list[Article]) -> str:
    """Generate a simple summary without AI when API fails."""
    lines = [f"# AI News Digest / AI 每日速递 - {datetime.now().strftime('%Y-%m-%d')}\n"]
    lines.append(f"*{len(articles)} articles collected (AI summary unavailable / AI 摘要不可用)*\n")

    by_category: dict[str, list[Article]] = {}
    for a in articles:
        by_category.setdefault(a.category, []).append(a)

    for cat, cat_articles in by_category.items():
        lines.append(f"\n## {cat.title()}\n")
        for a in cat_articles:
            lines.append(f"- **[{a.title}]({a.url})** ({a.source})")

    return "\n".join(lines)
