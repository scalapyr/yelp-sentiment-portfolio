"""Step 1: load the first 50,000 rows of the Yelp business and review JSON files into Snowflake RAW tables.
Paths come from BUSINESS_JSON_PATH / REVIEW_JSON_PATH in .env."""
import os
import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas
from dotenv import load_dotenv
from pathlib import Path  # Fixed: Added missing import

# Load environment variables
load_dotenv()

def get_connection():
    """Helper to create a fresh connection from .env variables"""
    return snowflake.connector.connect(
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        role=os.getenv('SNOWFLAKE_ROLE'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE'),
        database=os.getenv('SNOWFLAKE_DATABASE'),
        schema=os.getenv('SNOWFLAKE_SCHEMA')
    )

def load_to_snowflake(env_var_name, table_name, limit=50000):
    # 1. Pull the absolute path from .env
    raw_path = os.getenv(env_var_name)
    
    if not raw_path:
        print(f"❌ Error: Environment variable {env_var_name} is not set in .env")
        return

    file_path = Path(raw_path)

    if not file_path.exists():
        print(f"❌ File not found at: {file_path}")
        return

    print(f"🚀 Reading {limit} rows from {file_path.name}...")
    
    # 2. Use chunksize to handle large files
    with pd.read_json(file_path, lines=True, chunksize=limit) as reader:
        df = next(reader)
    
    # 3. Standardize column names for Snowflake (UPPERCASE)
    df.columns = [col.upper() for col in df.columns]
    
    # 4. Connect and Write
    conn = get_connection()
    try:
        print(f"📦 Writing to Snowflake table: {table_name}...")
        success, nchunks, nrows, _ = write_pandas(
            conn=conn,
            df=df,
            table_name=table_name,
            auto_create_table=True,
            quote_identifiers=False
        )
        if success:
            print(f"✅ Success! {nrows} rows loaded into {table_name}.")
    except Exception as e:
        print(f"❌ An error occurred: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    # Ensure these keys match exactly what's in .env
    load_to_snowflake('BUSINESS_JSON_PATH', 'RAW_BUSINESSES', limit=50000)
    load_to_snowflake('REVIEW_JSON_PATH', 'RAW_REVIEWS', limit=50000)