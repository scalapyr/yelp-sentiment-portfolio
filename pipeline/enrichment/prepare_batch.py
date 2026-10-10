"""Step 2b: build a Gemini Batch API request file (JSONL) for every review not yet enriched."""
import json
import pandas as pd
import os
from dotenv import load_dotenv
import snowflake.connector

load_dotenv()

conn = snowflake.connector.connect(
    user=os.getenv('SNOWFLAKE_USER'),
    password=os.getenv('SNOWFLAKE_PASSWORD'),
    account=os.getenv('SNOWFLAKE_ACCOUNT'),
    warehouse=os.getenv('SNOWFLAKE_WAREHOUSE'),
    database=os.getenv('SNOWFLAKE_DATABASE'),
    schema=os.getenv('SNOWFLAKE_SCHEMA')
)

def prepare_batch_file():
    # 1. get undone ones
    query = """
    SELECT 
        r.REVIEW_ID, 
        r.TEXT, 
        r.STARS,
        b.NAME, 
        b.CATEGORIES
    FROM YELP_DB.RAW.RAW_REVIEWS r
    JOIN YELP_DB.RAW.RAW_BUSINESSES b ON r.BUSINESS_ID = b.BUSINESS_ID
    WHERE r.REVIEW_ID NOT IN (
        SELECT REVIEW_ID FROM YELP_DB.RAW.RAW_REVIEWS_ENRICHED
    )
    """
    df = pd.read_sql(query, conn)

    system_prompt = """You are a data enrichment engine for a restaurant analytics platform. Given a customer review and business metadata, return ONLY a JSON object with these fields:
    {"sentiment": "positive"|"neutral"|"negative", 
    "intensity": 1-5 (how strongly expressed), 
    "primary_topic": "food_quality"|"service"|"ambiance"|"value"|"cleanliness", 
    "secondary_topics": [] (list of up to 2 additional topics from the same list),
    "is_local_regular": bool (signals if reviewer seems to be a regular)
    }

    EXAMPLES:
    Review: "The tacos were amazing, but it took forever to get a table."
    Output: {"sentiment": "positive", "intensity": 4, "primary_topic": "food_quality", "secondary_topics": ["service"], "is_local_regular": false}

    Review: "I come here every Tuesday. Best coffee in town."
    Output: {"sentiment": "positive", "intensity": 5, "primary_topic": "food_quality", "secondary_topics": [], "is_local_regular": true}
    
    Return nothing else. No explanation, no markdown."""

    with open("yelp_batch_input.jsonl", "w", encoding="utf-8") as f:
        for _, row in df.iterrows():
            user_prompt = f"""
            Business: {row['NAME']}
            Category: {row['CATEGORIES']}
            Stars: {row['STARS']}
            Review: {row['TEXT'][:400]}
            """
            
            # batch API request format with temperature config
            batch_request = {
                "key": row['REVIEW_ID'],
                "request": {
                    "contents": [
                        {"role": "user", "parts": [{"text": system_prompt + "\n\n" + user_prompt}]}
                    ],
                    "generation_config": {
                        "temperature": 0.1,
                        "response_mime_type": "application/json"
                    }
                }
            }
            f.write(json.dumps(batch_request) + "\n")
            
    print(f"✅ successfully generated batch file for {len(df)} records. ")

if __name__ == "__main__":
    prepare_batch_file()