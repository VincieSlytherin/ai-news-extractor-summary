#!/usr/bin/env python3
"""Streamlit web dashboard for AI News Aggregator.

Run: streamlit run dashboard.py
"""

from collections import Counter
from datetime import datetime
from pathlib import Path

import streamlit as st

from storage import Storage

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = str(DATA_DIR / "news.db")

st.set_page_config(
    page_title="AI News Aggregator",
    layout="wide",
)


@st.cache_resource
def get_db() -> Storage:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Storage(DB_PATH)


def main():
    st.title("AI News Aggregator")

    page = st.sidebar.radio(
        "Navigate",
        ["Overview", "Digest History", "Article Browser", "Run Logs"],
    )

    db = get_db()

    if page == "Overview":
        show_overview(db)
    elif page == "Digest History":
        show_digests(db)
    elif page == "Article Browser":
        show_articles(db)
    elif page == "Run Logs":
        show_runs(db)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def show_overview(db: Storage):
    st.header("Overview")

    runs = db.get_runs(limit=1)
    articles = db.get_articles(limit=2000)
    digests = db.get_digests(limit=60)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Articles in DB", len(articles))
    with col2:
        st.metric("Digests generated", len(digests))
    with col3:
        if runs:
            st.metric("Last run status", runs[0]["status"])
        else:
            st.metric("Last run status", "no runs yet")
    with col4:
        if runs:
            st.metric("Last run", runs[0]["started_at"][:16])
        else:
            st.metric("Last run", "-")

    if not articles:
        st.info("No data yet. Run the aggregator first:\n\n`python main.py --dry-run`")
        return

    st.divider()

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Articles by source (top 15)")
        source_counts = dict(
            sorted(Counter(a["source"] for a in articles).items(), key=lambda x: x[1], reverse=True)[:15]
        )
        st.bar_chart(source_counts)

    with col_b:
        st.subheader("Articles by category")
        cat_counts = dict(Counter(a["category"] for a in articles))
        st.bar_chart(cat_counts)


def show_digests(db: Storage):
    st.header("Digest History")

    digests = db.get_digests(limit=30)
    if not digests:
        st.info("No digests yet. Run the aggregator first.")
        return

    options = {
        f"{d['date']}  ({d['article_count']} articles)": d
        for d in digests
    }
    selected_label = st.selectbox("Select a digest", list(options.keys()))
    selected = options[selected_label]

    st.caption(f"Generated at: {selected['created_at']}")
    st.markdown(selected["markdown"], unsafe_allow_html=False)


def show_articles(db: Storage):
    st.header("Article Browser")

    col1, col2 = st.columns([3, 1])
    with col1:
        search = st.text_input("Search titles and summaries", "")
    with col2:
        all_articles = db.get_articles(limit=2000)
        categories = ["All"] + sorted({a["category"] for a in all_articles})
        category = st.selectbox("Category", categories)

    articles = db.get_articles(
        limit=300,
        search=search,
        category="" if category == "All" else category,
    )

    st.caption(f"{len(articles)} articles")

    for a in articles:
        date_str = a["created_at"][:10] if a.get("created_at") else ""
        header = f"**{a['title']}** — {a['source']}  `{date_str}`"
        with st.expander(header):
            st.markdown(f"[Open article]({a['url']})")
            if a.get("summary"):
                st.markdown(a["summary"])
            else:
                st.caption("No AI summary stored.")


def show_runs(db: Storage):
    st.header("Run Logs")

    runs = db.get_runs(limit=30)
    if not runs:
        st.info("No pipeline runs recorded yet.")
        return

    for run in runs:
        status = run["status"]
        icon = {"success": "OK", "error": "FAILED", "running": "RUNNING"}.get(status, status)

        duration = "-"
        if run.get("started_at") and run.get("finished_at"):
            start = datetime.fromisoformat(run["started_at"])
            end = datetime.fromisoformat(run["finished_at"])
            secs = int((end - start).total_seconds())
            duration = f"{secs // 60}m {secs % 60}s"

        label = f"[{icon}]  {run['started_at'][:16]}  —  scraped {run['articles_scraped'] or 0}, new {run['articles_new'] or 0}, took {duration}"

        with st.expander(label):
            col1, col2, col3 = st.columns(3)
            col1.metric("Scraped", run["articles_scraped"] or 0)
            col2.metric("New", run["articles_new"] or 0)
            col3.metric("Duration", duration)
            if run.get("error"):
                st.error(run["error"])


if __name__ == "__main__":
    main()
