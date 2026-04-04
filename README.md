# AI News Aggregator / AI 每日速递

A Python pipeline that concurrently scrapes 20+ AI/ML sources, deduplicates stories semantically using OpenAI embeddings, generates a bilingual (Chinese + English) digest, evaluates summary quality with LLM-as-judge, and exposes the data via a Streamlit dashboard, a REST API, and a ChromaDB-backed semantic search interface.

## Pipeline

```
Scrape (RSS/API/Web)
  → URL dedup (SQLite)
  → Semantic dedup (embeddings + cosine similarity)
  → Full-text extraction (trafilatura)
  → Per-article AI summaries (OpenAI, two-pass)
  → Digest generation (OpenAI, bilingual)
  → LLM-as-judge evaluation (faithfulness + coverage)
  → Email delivery (Gmail SMTP)
  → ChromaDB upsert (semantic search index)
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
# Full run: scrape + deduplicate + summarize + evaluate + email
python main.py

# Dry run: print digest to console, no email sent
python main.py --dry-run

# Skip semantic deduplication (saves embedding API tokens)
python main.py --no-semantic-dedup

# Skip LLM-as-judge evaluation (saves API tokens)
python main.py --skip-eval
```

### 4. Web dashboard

```bash
streamlit run dashboard.py
# Open http://localhost:8501
```

### 5. REST API

```bash
uvicorn api:app --reload
# Open http://localhost:8000/docs
```

## Services

| Service | Command | URL |
|---------|---------|-----|
| Dashboard | `streamlit run dashboard.py` | http://localhost:8501 |
| REST API | `uvicorn api:app` | http://localhost:8000 |
| API docs | — | http://localhost:8000/docs |

## How It Works

### 1. Scrape
Concurrently fetches all configured sources using `asyncio` + `httpx`. Supports three source types:
- **RSS/Atom** — feedparser, filters to last 3 days
- **Hacker News API** — top 60 stories filtered by 30+ AI keywords
- **Web** — BeautifulSoup CSS selector extraction

### 2. URL Deduplication
Filters out articles whose URLs are already stored in SQLite (`data/news.db`). Records are retained for 30 days.

### 3. Semantic Deduplication
Uses `text-embedding-3-small` to embed each article (title + content snippet), then computes cosine similarity against embeddings from the past 7 days. Articles above a 0.90 similarity threshold are dropped as near-duplicates — catching the same story covered by multiple outlets. Embeddings are stored in SQLite for future runs.

### 4. Full-Text Extraction
Fetches the full article page and extracts main body text using `trafilatura` (up to 5,000 characters). Falls back to the original RSS snippet if extraction fails. Only runs on articles that survived deduplication, minimising unnecessary requests.

### 5. AI Summarization (two-pass)
- **Pass 1** — Each article gets a detailed bilingual summary (3–5 sentences, specific facts/numbers/names), processed in batches of 10.
- **Pass 2** — All articles and their Pass 1 summaries are sent together to generate a thematic digest grouped by topic (LLM advances, industry news, research papers, engineering practices, agent tools).

### 6. LLM-as-Judge Evaluation
After summarization, `gpt-4o-mini` scores each summary on two dimensions (0–10):
- **Faithfulness** — does the summary accurately reflect the article without hallucinations?
- **Coverage** — does it cover the article's main points?

Scores are stored in SQLite and visualised as a quality trend chart in the dashboard's Overview page.

### 7. Email Delivery
Converts the Markdown digest to styled HTML and sends via Gmail SMTP with STARTTLS. Retries once on failure.

### 8. ChromaDB Semantic Search
Articles and their AI summaries are upserted into a persistent ChromaDB collection (`data/chroma/`) after each run. Pre-computed embeddings from the deduplication step are reused — no extra API calls. The Streamlit dashboard's **Semantic Search** page queries this collection by natural language.

## Project Structure

```
├── main.py            # Pipeline orchestration
├── scraper.py         # RSS, Hacker News, web scrapers + full-text enrichment
├── deduper.py         # Semantic deduplication via OpenAI embeddings
├── summarizer.py      # Two-pass bilingual summarization
├── evaluator.py       # LLM-as-judge faithfulness + coverage scoring
├── rag.py             # ChromaDB vector store: upsert + semantic search
├── api.py             # FastAPI REST service
├── emailer.py         # Gmail SMTP delivery with HTML template
├── storage.py         # SQLite: articles, digests, evaluations, run history
├── dashboard.py       # Streamlit web dashboard (5 pages)
├── config.yaml        # Source list and non-secret settings
├── .env.example       # Secret configuration template
├── requirements.txt   # Python dependencies
├── Dockerfile         # Container image
├── docker-compose.yml # Aggregator + dashboard + API services
├── k8s.yaml           # Kubernetes CronJob + Secret + PVC
└── data/              # Auto-created: SQLite DB + ChromaDB + run logs
    ├── news.db
    ├── chroma/
    └── run.log
```

## REST API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/stats` | Article counts, source breakdown, last run |
| GET | `/api/digests` | List of past digests (metadata) |
| GET | `/api/digest/{date}` | Full digest by date (YYYY-MM-DD) |
| GET | `/api/articles` | Articles with keyword search + category filter |
| GET | `/api/quality/trend` | Daily avg faithfulness + coverage scores |
| GET | `/api/quality/evaluations` | Per-article evaluation scores |
| GET | `/api/runs` | Pipeline run history |

Interactive docs available at `/docs`.

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
  model: "gpt-4o-mini"      # digest model
  eval_model: "gpt-4o-mini" # evaluation model (optional override)
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

# 2. Start persistent services
docker compose up dashboard api
# Dashboard: http://localhost:8501
# API:       http://localhost:8000

# 3. Run the aggregator once (scrape + summarize + evaluate + email)
docker compose run --rm aggregator

# Dry run (no email, no evaluation)
docker compose run --rm aggregator python main.py --dry-run --skip-eval
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
| OpenAI API (embeddings + eval) | ~$0.05/month (`text-embedding-3-small` + `gpt-4o-mini`) |
| Gmail SMTP | **Free** |

Each user runs their own instance with their own API key — no shared cost.

---

## Requirements

- Python 3.9+ (or Docker)
- An OpenAI API key
- A Gmail account with an App Password enabled
