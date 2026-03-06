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

## Docker Deployment

Docker lets you run the aggregator on any server without installing Python or dependencies.

### Option A: Docker (single run)

```bash
# 1. Clone and configure
git clone https://github.com/VincieSlytherin/ai-news-extractor-summary.git
cd ai-news-extractor-summary
cp .env.example .env
# Edit .env with your OpenAI key and Gmail credentials

# 2. Build the image
docker build -t ai-news-aggregator .

# 3. Run once (mounts ./data so the SQLite DB persists between runs)
docker run --rm --env-file .env -v "$(pwd)/data:/app/data" ai-news-aggregator

# Dry run (prints digest to console, no email sent)
docker run --rm --env-file .env -v "$(pwd)/data:/app/data" ai-news-aggregator python main.py --dry-run
```

### Option B: Docker Compose

```bash
# Run once
docker compose run --rm ai-news-aggregator

# Dry run
docker compose run --rm ai-news-aggregator python main.py --dry-run
```

### Scheduling with cron (Linux/Mac server)

Add to your crontab (`crontab -e`) to run every day at 8:00 AM:

```
0 8 * * * cd /path/to/ai-news-aggregator && docker compose run --rm ai-news-aggregator >> /var/log/ai-news.log 2>&1
```

---

## Kubernetes Deployment

For users who already have a Kubernetes cluster (e.g. self-hosted k3s, or a cloud cluster).

### 1. Build and push your image

```bash
docker build -t your-dockerhub-username/ai-news-aggregator:latest .
docker push your-dockerhub-username/ai-news-aggregator:latest
```

### 2. Edit k8s.yaml

Open [k8s.yaml](k8s.yaml) and fill in two things:

- **Secret** — your OpenAI API key and Gmail credentials (under `stringData`)
- **Image** — replace `your-dockerhub-username/ai-news-aggregator:latest` with your actual image

You can also change the schedule (`0 8 * * *` = daily at 8:00 AM UTC).

### 3. Deploy

```bash
kubectl apply -f k8s.yaml

# Verify the CronJob was created
kubectl get cronjob ai-news-aggregator

# Trigger a manual run to test
kubectl create job --from=cronjob/ai-news-aggregator ai-news-test

# Watch the logs
kubectl logs -l job-name=ai-news-test -f
```

### 4. Check results

```bash
# List past job runs
kubectl get jobs

# Get logs from the latest run
kubectl logs -l app=ai-news-aggregator --tail=50
```

---

## Cost Summary

| Component | Cost |
|-----------|------|
| Server / Kubernetes cluster | **Free** if self-hosted (e.g. your own machine, Oracle Cloud free tier) |
| Docker image hosting | **Free** (Docker Hub free tier) |
| OpenAI API | ~$1–10/month depending on model and run frequency |
| Gmail SMTP | **Free** |

Each user runs their own instance with their own API key — there is no shared cost.

---

## Requirements

- Python 3.9+ (or Docker)
- An OpenAI API key
- A Gmail account with an App Password enabled