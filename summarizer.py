import logging
from datetime import datetime

from openai import OpenAI

from storage import Article

logger = logging.getLogger(__name__)

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
- Focus on quality over quantity — skip low-value or duplicate content
- Output in clean Markdown format"""

USER_PROMPT_TEMPLATE = """Here are today's ({date}) collected AI/ML/Agent articles.
Please create a bilingual (中英双语) structured daily digest. Each article must have both Chinese and English summaries with the original link.

{articles_text}"""


def summarize(articles: list[Article], openai_config: dict) -> str:
    """Generate a structured summary of articles using OpenAI API."""
    if not articles:
        return "No new articles today."

    api_key = openai_config.get("api_key", "")
    model = openai_config.get("model", "gpt-4o-mini")
    max_tokens = openai_config.get("max_tokens", 4000)

    client = OpenAI(api_key=api_key)

    # Format articles for the prompt
    articles_text = _format_articles(articles)

    # If content is very long, split into batches
    if len(articles_text) > 30000:
        return _summarize_in_batches(client, model, max_tokens, articles)

    today = datetime.now().strftime("%Y-%m-%d")
    user_prompt = USER_PROMPT_TEMPLATE.format(date=today, articles_text=articles_text)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return _fallback_summary(articles)


def _summarize_in_batches(
    client: OpenAI, model: str, max_tokens: int, articles: list[Article]
) -> str:
    """Split articles into batches and summarize each, then merge."""
    batch_size = 15
    partial_summaries = []

    for i in range(0, len(articles), batch_size):
        batch = articles[i : i + batch_size]
        articles_text = _format_articles(batch)
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
                max_tokens=max_tokens,
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
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Merge summarization error: {e}")
        return "\n\n---\n\n".join(partial_summaries)


def _format_articles(articles: list[Article]) -> str:
    """Format articles into a text block for the prompt."""
    parts = []
    for i, a in enumerate(articles, 1):
        parts.append(
            f"[{i}] **{a.title}**\n"
            f"Source: {a.source} | Category: {a.category}\n"
            f"URL: {a.url}\n"
            f"Content: {a.content}\n"
        )
    return "\n".join(parts)


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
