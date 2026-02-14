# AI News Aggregator / AI 每日速递

A single-machine Python tool that crawls daily AI/Agent/ML news from top engineering blogs, personal blogs, and news sites, generates a **bilingual (Chinese + English)** digest using OpenAI, and emails it to you.

## Sources

| Category | Sources |
|---|---|
| News | Hacker News, TechCrunch AI, The Verge AI, ArXiv CS.AI |
| Engineering Blogs | Uber Engineering, Netflix TechBlog, Airbnb Tech, Stripe Engineering, Databricks, Anthropic |
| Personal Blogs | Andrej Karpathy, Chip Huyen, Lilian Weng, LangChain (Harrison Chase), Swyx, Latent.Space |
| Chinese Sites | 机器之心, 量子位, 36Kr AI |

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/VincieSlytherin/ai-news-extractor-summary.git
cd ai-news-extractor-summary
pip install -r requirements.txt
```

### 2. Configure secrets

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```
OPENAI_API_KEY=sk-your-key-here
EMAIL_PASSWORD=your-gmail-app-password
EMAIL_SENDER=your-email@gmail.com
EMAIL_RECIPIENT=your-email@gmail.com
```

> **Gmail App Password**: You need a Gmail App Password, not your regular password.
> Go to [Google Account](https://myaccount.google.com/) > Security > 2-Step Verification > App passwords, then generate one for "Mail".

### 3. Run

```bash
# Full run: scrape + summarize + send email
python main.py

# Dry run: scrape + summarize, print to console (no email sent)
python main.py --dry-run
```

## How It Works

```
Scrape (RSS/API/Web)  →  Deduplicate (SQLite)  →  Summarize (OpenAI)  →  Email (Gmail SMTP)
```

1. **Scrape** — Concurrently fetches all configured sources (RSS feeds, Hacker News API, web pages)
2. **Deduplicate** — Filters out articles already seen (stored in `data/news.db`)
3. **Summarize** — Sends articles to OpenAI to generate a bilingual digest grouped by theme
4. **Email** — Converts Markdown to styled HTML and sends via Gmail SMTP

## Project Structure

```
├── main.py            # Entry point and pipeline orchestration
├── scraper.py         # RSS, Hacker News API, and web scrapers
├── summarizer.py      # OpenAI-powered bilingual summary generation
├── emailer.py         # Gmail SMTP email sender with HTML template
├── storage.py         # SQLite storage for article deduplication
├── config.yaml        # Source list and non-secret settings
├── .env.example       # Template for secret configuration
├── requirements.txt   # Python dependencies
└── data/              # Auto-created: SQLite DB + run logs
```

## Configuration

### Add or remove sources

Edit `config.yaml`. Each source needs a `name`, `type`, `url`, and `category`:

```yaml
- name: "New Blog"
  type: "rss"          # rss | api | web
  url: "https://example.com/feed.xml"
  category: "engineering"
```

### Change the OpenAI model

Edit `config.yaml`:

```yaml
openai:
  model: "gpt-4o-mini"   # or "gpt-4o", "gpt-4-turbo", etc.
  max_tokens: 4000
```

## Requirements

- Python 3.9+
- An OpenAI API key
- A Gmail account with an App Password enabled