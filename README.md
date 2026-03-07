# AI News Aggregator / AI 每日速递

A Python pipeline that concurrently scrapes 20+ AI/ML sources, deduplicates stories semantically using OpenAI embeddings, generates a bilingual (Chinese + English) digest, emails it via Gmail, and exposes a web dashboard to browse past digests and articles.

## Pipeline

```
Scrape (RSS/API/Web)
  → URL dedup (SQLite)
  → Semantic dedup (embeddings + cosine similarity)
  → Full-text extraction (trafilatura)
  → Per-article AI summaries (OpenAI)
  → Digest generation (OpenAI, bilingual)
  → Email delivery (Gmail SMTP)
  → Web dashboard (Streamlit)
```

## Sources

| Category | Sources |
|---|---|
| News | Hacker News, TechCrunch AI, The Verge AI, ArXiv CS.AI |
| Engineering Blogs | Uber Engineering, Netflix TechBlog, Airbnb Tech, Stripe Engineering, Databricks, Anthropic |
| Personal Blogs | Andrej Karpathy, Chip Huyen, Lilian Weng, LangChain, Swyx, Latent.Space |
| Chinese Sites | 机器之心, 量子位, 36Kr AI |

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/VincieSlytherin/ai-news-extractor-summary.git
cd ai-news-extractor-summary
pip install -r requirements.txt
```

### 2. Configure secrets

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

> **Gmail App Password**: Go to [Google Account](https://myaccount.google.com/) > Security > 2-Step Verification > App passwords, generate one for "Mail".

### 3. Run

```bash
# Full run: scrape + deduplicate + summarize + email
python main.py

# Dry run: print digest to console, no email sent
python main.py --dry-run

# Skip semantic deduplication (saves embedding API tokens)
python main.py --no-semantic-dedup
```

### 4. Web dashboard

```bash
streamlit run dashboard.py
# Open http://localhost:8501
```

## How It Works

### 1. Scrape
Concurrently fetches all configured sources using `asyncio` + `httpx`. Supports three source types:
- **RSS/Atom** — feedparser, filters to last 3 days
- **Hacker News API** — top 60 stories filtered by 30+ AI keywords
- **Web** — BeautifulSoup CSS selector extraction

### 2. URL Deduplication
Filters out articles whose URLs are already stored in SQLite (`data/news.db`). Records are retained for 30 days.

### 3. Semantic Deduplication
Uses `text-embedding-3-small` to embed each article (title + content snippet), then computes cosine similarity against embeddings from the past 7 days. Articles above a 0.90 similarity threshold are dropped as near-duplicates — catching the same story covered by multiple outlets. Embeddings are stored in the DB for future runs.

### 4. Full-Text Extraction
Fetches the full article page and extracts main body text using `trafilatura` (up to 5,000 characters). Falls back to the original RSS snippet if extraction fails or returns too little text. Only runs on articles that survived deduplication, minimising unnecessary requests.

### 5. AI Summarization (two-pass)
- **Pass 1** — Each article gets a detailed bilingual summary (3–5 sentences, specific facts/numbers/names), processed in batches of 10.
- **Pass 2** — All articles and their Pass 1 summaries are sent together to generate a thematic digest grouped by topic (LLM advances, industry news, research papers, engineering practices, agent tools).

### 6. Email Delivery
Converts the Markdown digest to styled HTML and sends via Gmail SMTP with STARTTLS. Retries once on failure.

### 7. Web Dashboard
Streamlit app with four pages:
- **Overview** — article counts, last run status, charts by source and category
- **Digest History** — browse and read any past digest
- **Article Browser** — search and filter all stored articles with their AI summaries
- **Run Logs** — history of pipeline runs with status, duration, and error details

## Project Structure

```
├── main.py            # Pipeline orchestration
├── scraper.py         # RSS, Hacker News, web scrapers + full-text enrichment
├── deduper.py         # Semantic deduplication via OpenAI embeddings
├── summarizer.py      # Two-pass bilingual summarization
├── emailer.py         # Gmail SMTP delivery with HTML template
├── storage.py         # SQLite: articles, digests, run history
├── dashboard.py       # Streamlit web dashboard
├── config.yaml        # Source list and non-secret settings
├── .env.example       # Secret configuration template
├── requirements.txt   # Python dependencies
├── Dockerfile         # Container image
├── docker-compose.yml # Aggregator + dashboard services
├── k8s.yaml           # Kubernetes CronJob + Secret + PVC
└── data/              # Auto-created: SQLite DB + run logs
```

## Configuration

### Add or remove sources

Edit `config.yaml`:

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

## Docker Deployment

### Run with Docker Compose

```bash
# 1. Clone and configure
git clone https://github.com/VincieSlytherin/ai-news-extractor-summary.git
cd ai-news-extractor-summary
cp .env.example .env
# Edit .env with your credentials

# 2. Start the dashboard (persistent)
docker compose up dashboard
# Open http://localhost:8501

# 3. Run the aggregator once (scrape + summarize + email)
docker compose run --rm aggregator

# Dry run (no email)
docker compose run --rm aggregator python main.py --dry-run
```

### Schedule with cron (Linux/Mac server)

```
0 8 * * * cd /path/to/ai-news-aggregator && docker compose run --rm aggregator >> /var/log/ai-news.log 2>&1
```

---

## Kubernetes Deployment

For users with an existing Kubernetes cluster (e.g. self-hosted k3s, or a cloud cluster).

### 1. Build and push your image

```bash
docker build -t your-dockerhub-username/ai-news-aggregator:latest .
docker push your-dockerhub-username/ai-news-aggregator:latest
```

### 2. Edit k8s.yaml

Open [k8s.yaml](k8s.yaml) and fill in:

- **Secret** — your credentials under `stringData`
- **Image** — replace `your-dockerhub-username/ai-news-aggregator:latest`

Change the schedule if needed (`0 8 * * *` = daily at 8:00 AM UTC).

### 3. Deploy

```bash
kubectl apply -f k8s.yaml

# Verify
kubectl get cronjob ai-news-aggregator

# Trigger a manual test run
kubectl create job --from=cronjob/ai-news-aggregator ai-news-test
kubectl logs -l job-name=ai-news-test -f
```

---

## Cost Summary

| Component | Cost |
|-----------|------|
| Server / cluster | **Free** if self-hosted (e.g. Oracle Cloud free tier) |
| Docker Hub | **Free** (free tier) |
| OpenAI API (summaries) | ~$1–10/month depending on model and frequency |
| OpenAI API (embeddings) | ~$0.02/month (`text-embedding-3-small`) |
| Gmail SMTP | **Free** |

Each user runs their own instance with their own API key — no shared cost.

---

## Requirements

- Python 3.9+ (or Docker)
- An OpenAI API key
- A Gmail account with an App Password enabled
