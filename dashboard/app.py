"""Streamlit dashboard for LLM-enriched Yelp review sentiment.

Reads only the small aggregate CSVs in data/demo/ (built by build_demo_data.py),
so it needs no database connection, API key or row-level review data.
Set DEMO_DATA_DIR to point at a different folder of the same files.
"""
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA_DIR = Path(os.getenv("DEMO_DATA_DIR", Path(__file__).resolve().parent.parent / "data" / "demo"))

SENTIMENT_COLORS = {"positive": "#2ECC71", "negative": "#E24B4A", "neutral": "#BDC3C7"}
MIN_TOPICS_PER_CATEGORY = 4  # heatmap rows need at least this many topic cells

st.set_page_config(page_title="Yelp Sentiment Analytics", layout="wide")
st.title("Yelp Restaurant Sentiment Analytics")
st.caption("LLM-enriched review analysis · Gemini API · Snowflake · dbt · Streamlit")


@st.cache_data
def load_data():
    return (
        pd.read_csv(DATA_DIR / "business_summary.csv"),
        pd.read_csv(DATA_DIR / "topic_sentiment.csv"),
        pd.read_csv(DATA_DIR / "intensity_by_sentiment.csv"),
        pd.read_csv(DATA_DIR / "category_topic.csv"),
    )


summary, topics, intensity, cat_topic = load_data()

# ── row 1: headline metrics ─────────────────────────────────────────────────
st.subheader("Overview")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Reviews analysed", f"{topics['REVIEW_COUNT'].sum():,}")
c2.metric("Businesses (>5 reviews)", f"{len(summary):,}")
c3.metric("Avg % positive", f"{summary['PCT_POSITIVE'].mean():.1f}%")
c4.metric("Avg % negative", f"{summary['PCT_NEGATIVE'].mean():.1f}%")
c5.metric("Avg sentiment-stars gap", f"{summary['SENTIMENT_STARS_GAP'].mean():.2f}")
st.caption(
    "Business-level figures cover businesses with more than 5 reviews. "
    "Business names and Yelp IDs are replaced with anonymous labels."
)

st.divider()

# ── row 2: sentiment-stars gap scatter ─────────────────────────────────────
st.subheader("Sentiment vs star rating gap")
st.caption(
    "Gap = average stars minus an LLM sentiment score (positive 4.5, neutral 3.0, negative 1.5). "
    "Positive gap: stars are more generous than the words."
)
fig1 = px.scatter(
    summary,
    x="AVG_STARS",
    y="PCT_POSITIVE",
    size="TOTAL_REVIEWS",
    color="SENTIMENT_STARS_GAP",
    color_continuous_scale="Portland",
    hover_data=["BUSINESS", "TOP_TOPIC", "PCT_LOCAL_REGULARS"],
    labels={
        "AVG_STARS": "Avg star rating",
        "PCT_POSITIVE": "% positive sentiment (LLM)",
        "SENTIMENT_STARS_GAP": "Sentiment-stars gap",
    },
    title="Star rating vs LLM sentiment — sized by review volume",
)
st.plotly_chart(fig1, use_container_width=True)

st.divider()

# ── row 3: topic breakdown ─────────────────────────────────────────────────
st.subheader("Topic breakdown: volume, praise and complaints")
col_a, col_b, col_c = st.columns(3)

with col_a:
    total = topics.groupby("PRIMARY_TOPIC")["REVIEW_COUNT"].sum().reset_index()
    fig = px.bar(
        total.sort_values("REVIEW_COUNT"), x="REVIEW_COUNT", y="PRIMARY_TOPIC",
        orientation="h", title="Total volume", color_discrete_sequence=["#34495E"],
        labels={"REVIEW_COUNT": "Reviews", "PRIMARY_TOPIC": "Topic"},
    )
    st.plotly_chart(fig, use_container_width=True)

with col_b:
    pos = topics[topics["SENTIMENT"] == "positive"].sort_values("REVIEW_COUNT")
    fig = px.bar(
        pos, x="REVIEW_COUNT", y="PRIMARY_TOPIC", orientation="h",
        title="Positive drivers", color_discrete_sequence=["#27AE60"],
        labels={"REVIEW_COUNT": "Positive reviews", "PRIMARY_TOPIC": "Topic"},
    )
    st.plotly_chart(fig, use_container_width=True)

with col_c:
    neg = topics[topics["SENTIMENT"] == "negative"].sort_values("REVIEW_COUNT")
    fig = px.bar(
        neg, x="REVIEW_COUNT", y="PRIMARY_TOPIC", orientation="h",
        title="Negative pain points", color_discrete_sequence=["#E74C3C"],
        labels={"REVIEW_COUNT": "Negative reviews", "PRIMARY_TOPIC": "Topic"},
    )
    st.plotly_chart(fig, use_container_width=True)

# ── row 4: local regular signal ────────────────────────────────────────────
st.subheader("Local regular signal")
st.caption("Do businesses with more LLM-detected local regulars show different sentiment?")
fig4 = px.scatter(
    summary[summary["PCT_LOCAL_REGULARS"] > 0],
    x="PCT_LOCAL_REGULARS",
    y="PCT_POSITIVE",
    size="TOTAL_REVIEWS",
    color="AVG_STARS",
    color_continuous_scale="Viridis",
    hover_data=["BUSINESS"],
    labels={
        "PCT_LOCAL_REGULARS": "% local regulars (LLM)",
        "PCT_POSITIVE": "% positive sentiment",
        "AVG_STARS": "Avg stars",
    },
    title="Local regular concentration vs positive sentiment",
)
st.plotly_chart(fig4, use_container_width=True)

st.divider()

# ── row 5: biggest gap table ───────────────────────────────────────────────
st.subheader("Businesses with the largest sentiment-stars gap")
st.caption("Where star ratings are most generous relative to what reviewers actually wrote")
gap_table = summary.nlargest(20, "SENTIMENT_STARS_GAP")[[
    "BUSINESS", "AVG_STARS", "PCT_POSITIVE", "PCT_NEGATIVE",
    "SENTIMENT_STARS_GAP", "TOP_TOPIC", "TOTAL_REVIEWS",
]].reset_index(drop=True)
st.dataframe(gap_table, use_container_width=True)

# ── row 6: sentiment composition by topic ──────────────────────────────────
st.subheader("Sentiment composition by topic")
fig5 = px.bar(
    topics, x="PRIMARY_TOPIC", y="REVIEW_COUNT", color="SENTIMENT", barmode="group",
    title="Topic sentiment distribution", color_discrete_map=SENTIMENT_COLORS,
    labels={"REVIEW_COUNT": "Number of reviews", "PRIMARY_TOPIC": "Topic"},
)
st.plotly_chart(fig5, use_container_width=True)

# ── row 7: emotional intensity vs sentiment ────────────────────────────────
st.subheader("Emotional intensity vs sentiment")
st.caption("Share of reviews at each LLM-scored intensity level, within each sentiment")
dist = intensity.copy()
dist["pct"] = (
    dist.groupby("SENTIMENT")["REVIEW_COUNT"].transform(lambda x: x / x.sum() * 100).round(1)
)
dist["INTENSITY"] = dist["INTENSITY"].astype(str)
fig6 = px.bar(
    dist, x="INTENSITY", y="pct", color="SENTIMENT", barmode="group",
    title="Intensity score distribution by sentiment", color_discrete_map=SENTIMENT_COLORS,
    labels={"INTENSITY": "Intensity score (1–5)", "pct": "% of reviews", "SENTIMENT": "Sentiment"},
)
fig6.update_layout(xaxis=dict(categoryorder="array", categoryarray=["1", "2", "3", "4", "5"]))
st.plotly_chart(fig6, use_container_width=True)

# ── row 8: category x topic heatmaps ───────────────────────────────────────
st.subheader("Sentiment by restaurant category and topic")
st.caption(
    "Left: where categories earn praise. Right: where they generate complaints. "
    "Cells need at least 10 reviews; n/a = not enough data."
)


def heatmap(value_col, colorscale, title, bar_title):
    pivot = cat_topic.pivot(index="PRIMARY_CATEGORY", columns="PRIMARY_TOPIC", values=value_col)
    pivot = pivot[pivot.notna().sum(axis=1) >= MIN_TOPICS_PER_CATEGORY]
    text = pivot.map(lambda x: f"{x:.1f}%" if pd.notna(x) else "n/a").values
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values, x=pivot.columns.tolist(), y=pivot.index.tolist(),
        colorscale=colorscale, text=text, texttemplate="%{text}",
        colorbar=dict(title=bar_title), zmin=0, zmax=100,
    ))
    fig.update_layout(
        title=title, height=max(400, len(pivot) * 30), margin=dict(l=140, r=40, t=60, b=40)
    )
    return fig


h1, h2 = st.columns(2)
with h1:
    st.plotly_chart(heatmap("PCT_POSITIVE", "Greens", "% positive by category and topic", "% positive"),
                    use_container_width=True)
with h2:
    st.plotly_chart(heatmap("PCT_NEGATIVE", "Reds", "% negative by category and topic", "% negative"),
                    use_container_width=True)

st.divider()
st.caption(
    "Data: derived from a 50,000-review sample of the Yelp Open Dataset (educational use). "
    "Only aggregate statistics are shown; no review text or reviewer information is included."
)
