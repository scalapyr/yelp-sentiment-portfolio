"""Helper: list uploaded files and Batch API jobs on the Gemini account."""
from google import genai
import os
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

# List all files currently stored in your Gemini/Google Cloud project
print("--- Current Files on Cloud ---")
for f in client.files.list():
    print(f"Display Name: {f.display_name} | Name: {f.name} | State: {f.state}")

# check job status
print("--- Current Batch Jobs ---")
for job in client.batches.list():
    print(f"Job ID: {job.name} | Status: {job.state} | Created: {job.create_time}")