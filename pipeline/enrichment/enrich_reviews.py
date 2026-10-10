"""Step 2a (first version): synchronous enrichment loop sized for the Gemini free tier
(~15 requests/min), writing results straight to Snowflake in small batches."""
import os
import json
import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas
from dotenv import load_dotenv
import google.generativeai as genai
import time

load_dotenv()

# Configure and setup Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel(
    model_name='gemini-2.5-flash-lite',
    generation_config={
        "response_mime_type": "application/json",
        "temperature": 0.1
    }
)

def get_snowflake_conn():
    return snowflake.connector.connect(
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        role=os.getenv('SNOWFLAKE_ROLE'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE'),
        database=os.getenv('SNOWFLAKE_DATABASE'),
        schema='RAW'
    )

def enrich_review(row):
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
    
    user_prompt = f"""
    Business: {row['NAME']}
    Category: {row['CATEGORIES']}
    Stars: {row['STARS_REVIEW']}
    Review: {row['TEXT'][:400]}
    """
    
    try:
        response = model.generate_content([system_prompt, user_prompt])
        return json.loads(response.text) # JSON mode returns clean text directly
    except Exception as e:
        print(f"Error processing row: {e}")
        return None

if __name__ == "__main__":
    from tqdm import tqdm
    import pandas as pd
    import time
    
    conn = get_snowflake_conn()
    
    # 1. Smart SQL Logic (Incremental vs Initial)
    # skips the ones enriched already
    incremental_query = """
    SELECT r.REVIEW_ID, r.TEXT, r.STARS as STARS_REVIEW, b.NAME, b.CATEGORIES
    FROM RAW_REVIEWS r
    JOIN RAW_BUSINESSES b ON r.BUSINESS_ID = b.BUSINESS_ID
    LEFT JOIN RAW_REVIEWS_ENRICHED e ON r.REVIEW_ID = e.REVIEW_ID
    WHERE e.REVIEW_ID IS NULL 
    LIMIT 900
    """
    
    initial_query = """
    SELECT r.REVIEW_ID, r.TEXT, r.STARS as STARS_REVIEW, b.NAME, b.CATEGORIES
    FROM RAW_REVIEWS r
    JOIN RAW_BUSINESSES b ON r.BUSINESS_ID = b.BUSINESS_ID
    LIMIT 900
    """

    try:
        df = pd.read_sql(incremental_query, conn)
        print(f"Incremental mode active. Found {len(df)} new reviews.")
    except Exception:
        print("Enriched table not found. Running initial query to create table...")
        df = pd.read_sql(initial_query, conn)

    enriched_data = []
    
    # 2. The Steady-State Processing Loop
    print(f"Starting 1-hour enrichment run (900 reviews)...")
    for i, row in tqdm(df.iterrows(), total=len(df)):
        result = enrich_review(row)
        
        if result:
            result['REVIEW_ID'] = row['REVIEW_ID']
            enriched_data.append(result)
            
        # 3. Automated Batch Save (Every 25 rows for higher safety)
        if len(enriched_data) >= 25:
            try:
                batch_df = pd.DataFrame(enriched_data)
                batch_df.columns = [col.upper() for col in batch_df.columns]
                
                # Appends to the table; creates it if it's the first batch
                write_pandas(
                    conn, 
                    batch_df, 
                    'RAW_REVIEWS_ENRICHED', 
                    auto_create_table=True, 
                    overwrite=False
                )
                enriched_data = [] # Flush memory
            except Exception as e:
                print(f"\n[Warning] Batch save failed at index {i}: {e}. Retrying with next batch.")
        
        # 4. Free-Tier Optimized Timeout
        # stay slightly under the 15 RPM limit.
        time.sleep(4.1) 

    # 4. Final Cleanup (Saves the last partial batch)
    if enriched_data:
        final_batch_df = pd.DataFrame(enriched_data)
        final_batch_df.columns = [col.upper() for col in final_batch_df.columns]
        write_pandas(conn, final_batch_df, 'RAW_REVIEWS_ENRICHED', auto_create_table=True, overwrite=False)

    print("\n✅ Hour-long session complete. All data synced to Snowflake.")
    conn.close()