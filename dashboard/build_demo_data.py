"""Build the small, anonymized aggregate files the dashboard reads.

Run this once, locally, against CSV exports of two Snowflake tables:
  * ANALYTICS.INT_REVIEWS_CLEAN          (silver layer, one row per review)
  * ANALYTICS.BUSINESS_SENTIMENT_SUMMARY (gold layer, one row per business)
  * RAW.RAW_BUSINESSES                   (only BUSINESS_ID and CATEGORIES are read)

Outputs (data/demo/):
  business_summary.csv        gold summary, Yelp business_id replaced by an anonymous label
  topic_sentiment.csv         review counts by primary topic x sentiment
  intensity_by_sentiment.csv  review counts by sentiment x intensity (1-5)
  category_topic.csv          % positive / % negative by cuisine category x topic (n >= 10)

No review text, user IDs, business names/addresses or Yelp IDs are written.

Usage:
  python dashboard/build_demo_data.py \
      --reviews  path/to/int_reviews_clean.csv \
      --summary  path/to/business_sentiment_summary.csv \
      --businesses path/to/raw_businesses.csv
"""
import argparse
from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "demo"

# Maps Yelp category tags to a single primary cuisine / format label.
CATEGORY_MAP = {
    # cuisine
    "chinese": "Chinese", "mexican": "Mexican", "italian": "Italian",
    "japanese": "Japanese", "thai": "Thai", "indian": "Indian",
    "mediterranean": "Mediterranean", "french": "French",
    "vietnamese": "Vietnamese", "korean": "Korean",
    "american (traditional)": "American", "american (new)": "American",
    "southern": "Southern", "cajun/creole": "Cajun/Creole",
    "greek": "Greek", "middle eastern": "Middle Eastern",
    "spanish": "Spanish", "caribbean": "Caribbean",
    # format / type
    "fast food": "Fast Food", "burgers": "Burgers",
    "pizza": "Pizza", "sandwiches": "Sandwiches",
    "sushi bars": "Sushi", "seafood": "Seafood",
    "steakhouses": "Steakhouses", "buffets": "Buffets",
    "food trucks": "Food Trucks", "diners": "Diners",
    # cafe / drink
    "coffee & tea": "Coffee & Tea", "cafes": "Cafes",
    "bars": "Bars", "pubs": "Pubs", "wine bars": "Wine Bars",
}

MIN_REVIEWS_PER_CELL = 10


def primary_category(raw):
    """First tag in the comma-separated Yelp category list that maps to a label."""
    if not isinstance(raw, str):
        return None
    for part in (p.strip().lower() for p in raw.split(",")):
        if part in CATEGORY_MAP:
            return CATEGORY_MAP[part]
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reviews", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--businesses", required=True)
    args = ap.parse_args()

    reviews = pd.read_csv(
        args.reviews,
        usecols=["BUSINESS_ID", "STARS", "SENTIMENT", "PRIMARY_TOPIC", "INTENSITY", "QUALITY_STATUS"],
    )
    reviews = reviews[reviews["QUALITY_STATUS"] == "clean"]
    summary = pd.read_csv(args.summary)
    businesses = pd.read_csv(args.businesses, usecols=["BUSINESS_ID", "CATEGORIES"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Business summary with anonymous labels (ordered by review volume, then gap).
    summary = summary.sort_values(
        ["TOTAL_REVIEWS", "SENTIMENT_STARS_GAP"], ascending=[False, False]
    ).reset_index(drop=True)
    summary.insert(0, "BUSINESS", [f"Business {i + 1:04d}" for i in range(len(summary))])
    summary = summary.drop(columns=["BUSINESS_ID"])
    summary.to_csv(OUT_DIR / "business_summary.csv", index=False)

    # 2. Topic x sentiment counts.
    topic_sentiment = (
        reviews.groupby(["PRIMARY_TOPIC", "SENTIMENT"]).size().reset_index(name="REVIEW_COUNT")
    )
    topic_sentiment.to_csv(OUT_DIR / "topic_sentiment.csv", index=False)

    # 3. Sentiment x intensity counts.
    intensity = reviews.groupby(["SENTIMENT", "INTENSITY"]).size().reset_index(name="REVIEW_COUNT")
    intensity.to_csv(OUT_DIR / "intensity_by_sentiment.csv", index=False)

    # 4. Cuisine category x topic.
    businesses["PRIMARY_CATEGORY"] = businesses["CATEGORIES"].apply(primary_category)
    food = businesses.dropna(subset=["PRIMARY_CATEGORY"])[["BUSINESS_ID", "PRIMARY_CATEGORY"]]
    df = reviews.merge(food, on="BUSINESS_ID", how="inner")
    cat_topic = (
        df.groupby(["PRIMARY_CATEGORY", "PRIMARY_TOPIC"])
        .agg(
            REVIEW_COUNT=("SENTIMENT", "size"),
            AVG_STARS=("STARS", "mean"),
            AVG_INTENSITY=("INTENSITY", "mean"),
            PCT_POSITIVE=("SENTIMENT", lambda s: (s == "positive").mean() * 100),
            PCT_NEGATIVE=("SENTIMENT", lambda s: (s == "negative").mean() * 100),
        )
        .round(2)
        .reset_index()
    )
    cat_topic = cat_topic[cat_topic["REVIEW_COUNT"] >= MIN_REVIEWS_PER_CELL]
    cat_topic.to_csv(OUT_DIR / "category_topic.csv", index=False)

    print(f"Clean reviews aggregated: {len(reviews):,}")
    for f in sorted(OUT_DIR.glob("*.csv")):
        print(f"  {f.name:28s} {sum(1 for _ in open(f)) - 1:6,d} rows  {f.stat().st_size / 1024:6.1f} KB")


if __name__ == "__main__":
    main()
