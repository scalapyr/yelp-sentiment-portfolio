"""Step 3: load enriched_reviews.jsonl (status == ok rows) into RAW.RAW_REVIEWS_ENRICHED."""
import os
from dotenv import load_dotenv
import json
import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

# 1. Load credentials
load_dotenv()

def upload_to_snowflake():
    # Establish Connection
    conn = snowflake.connector.connect(
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        role=os.getenv('SNOWFLAKE_ROLE'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE'),
        database=os.getenv('SNOWFLAKE_DATABASE'),
        schema='RAW'
    )

    file_path = 'enriched_reviews.jsonl'
    
    # 2. Parse JSONL
    print(f"Reading and filtering {file_path}...")
    df = pd.read_json(file_path, lines=True)

    # 3. Filter for 'ok' status and then drop the unsuccessful data
    df = df[df['status'] == 'ok'].copy()
    df = df.drop(columns=['status'])

    # Boolean: force conversion to actual bool to prevent numeric/float casting (0.00e+00)
    if 'is_local_regular' in df.columns:
        # This converts 0, 0.0, None to False and non-zero/True to True
        df['is_local_regular'] = df['is_local_regular'].astype(bool)

    # Intensity: ensure it's an integer
    if 'intensity' in df.columns:
        df['intensity'] = pd.to_numeric(df['intensity'], errors='coerce').fillna(0).astype(int)

    # Indexing Warning: Resets the index to a standard RangeIndex
    df = df.reset_index(drop=True)
    # ----------------------------------

    # 4. Map Python types to Snowflake Table types
    # Secondary_topics is a VARIANT (list/json in Snowflake), 
    df['secondary_topics'] = df['secondary_topics'].apply(lambda x: json.dumps(x) if isinstance(x, (list, dict)) else x)

    # 5. Match Snowflake Column Naming (Uppercase)
    df.columns = [c.upper() for c in df.columns]

    # 6. Strict Column Alignment
    expected_columns = ['SENTIMENT', 'INTENSITY', 'PRIMARY_TOPIC', 'SECONDARY_TOPICS', 'IS_LOCAL_REGULAR', 'REVIEW_ID']
    df = df[expected_columns]

    # 7. Upload
    table_name = 'RAW_REVIEWS_ENRICHED'
    print(f"Uploading {len(df)} rows to {table_name}...")
    
    try:
        success, nchunks, nrows, _ = write_pandas(
            conn=conn,
            df=df,
            table_name=table_name,
            auto_create_table=False  # table is already created
        )
        
        if success:
            print(f"Successfully uploaded {nrows} rows.")
    except Exception as e:
        print(f"Upload failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    upload_to_snowflake()