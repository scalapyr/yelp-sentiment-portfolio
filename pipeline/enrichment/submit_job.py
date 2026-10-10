"""Step 2b: upload the batch-request JSONL and submit a Gemini Batch API job."""
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize the client
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

def submit_batch():
    batch_file_path = os.getenv("BATCH_INPUT_FILE", "yelp_batch_input.jsonl")
    
    print(f"1. Attempting to upload: {batch_file_path}")
    
    try:
        uploaded_file = client.files.upload(
            file=batch_file_path, 
            config=types.UploadFileConfig(
                display_name="yelp_enrichment_50k",
                mime_type='application/x-jsonlines')
        )
        print(f"✅ Upload successful! Cloud URI: {uploaded_file.name}")

        print("2. Creating Batch Job (Gemini 2.5 Flash-Lite)...")
        
        # Submitting the job to Google's batch cluster
        batch_job = client.batches.create(
            model="gemini-2.5-flash-lite",
            src=uploaded_file.name,
            config=types.CreateBatchJobConfig(display_name="yelp_massive_job_2026")
        )

        print("\n" + "="*30)
        print("🚀 JOB SUBMITTED SUCCESSFULLY!")
        print(f"Job Name: {batch_job.name}")
        print("="*30)
        
        # Save the Job Name for retrieval later
        with open("current_job_id.txt", "w") as f:
            f.write(batch_job.name)
        
        print("\nJob Name saved to current_job_id.txt.")

    except Exception as e:
        print(f"❌ Error during submission: {e}")

if __name__ == "__main__":
    submit_batch()