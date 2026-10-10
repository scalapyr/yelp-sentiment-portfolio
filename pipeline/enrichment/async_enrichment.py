"""Step 2c (final run): async enrichment of the batch-request JSONL with
bounded concurrency, a sliding-window RPM limiter, 429 backoff and a
checkpoint file so interrupted runs resume where they stopped."""
import asyncio
import json
import os
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

# ── config ────────────────────────────────────────────────────────────────────
MODEL           = "gemini-2.5-flash-lite"
MAX_CONCURRENT  = 20
RPM_LIMIT       = 500
INPUT_FILE      = os.getenv("BATCH_INPUT_FILE", "yelp_batch_input.jsonl")
OUTPUT_FILE     = "enriched_reviews.jsonl"
CHECKPOINT_FILE = "checkpoint.txt"
BATCH_SIZE      = 100

# ── single record enrichment ──────────────────────────────────────────────────
async def enrich_one(
    row: dict,
    semaphore: asyncio.Semaphore,
    rpm_tracker: list,
) -> dict:
    review_id   = row["key"]
    prompt_text = row["request"]["contents"][0]["parts"][0]["text"]
    gen_config  = row["request"].get("generation_config", {})

    async with semaphore:
        # ── RPM throttle ──────────────────────────────────────────────────────
        now = time.monotonic()
        rpm_tracker[:] = [t for t in rpm_tracker if now - t < 60]
        if len(rpm_tracker) >= RPM_LIMIT:
            sleep_for = 60 - (now - rpm_tracker[0]) + 0.5
            await asyncio.sleep(sleep_for)
        rpm_tracker.append(time.monotonic())

        # ── API call with retry ───────────────────────────────────────────────
        for attempt in range(4):
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=MODEL,
                    contents=prompt_text,
                    config=types.GenerateContentConfig(
                        temperature=gen_config.get("temperature", 0.1),
                        response_mime_type=gen_config.get(
                            "response_mime_type", "application/json"
                        ),
                    ),
                )
                parsed = json.loads(response.text)
                parsed["review_id"] = review_id
                parsed["status"]    = "ok"
                return parsed

            except json.JSONDecodeError:
                return {
                    "review_id": review_id,
                    "status":    "bad_json",
                    "raw":       response.text,
                }
            except Exception as e:
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    wait = 2 ** attempt * 10
                    print(f"  429 on {review_id}, retry {attempt+1} in {wait}s")
                    await asyncio.sleep(wait)
                else:
                    return {
                        "review_id": review_id,
                        "status":    "error",
                        "error":     msg,
                    }

        return {"review_id": review_id, "status": "failed_after_retries"}

# ── checkpoint helpers ────────────────────────────────────────────────────────
def load_checkpoint() -> set:
    if not os.path.exists(CHECKPOINT_FILE):
        return set()
    with open(CHECKPOINT_FILE) as f:
        return set(line.strip() for line in f if line.strip())

def save_checkpoint(review_ids: list):
    with open(CHECKPOINT_FILE, "a") as f:
        for rid in review_ids:
            f.write(str(rid) + "\n")

def append_results(results: list):
    with open(OUTPUT_FILE, "a") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

# ── main ──────────────────────────────────────────────────────────────────────
async def main():
    records = []
    with open(INPUT_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    print(f"Loaded {len(records)} records from {INPUT_FILE}")

    done_ids  = load_checkpoint()
    remaining = [r for r in records if str(r["key"]) not in done_ids]
    print(f"Already done: {len(done_ids)} | Remaining: {len(remaining)}")

    if not remaining:
        print("Nothing left to process — all records already in checkpoint.")
        return

    semaphore   = asyncio.Semaphore(MAX_CONCURRENT)
    rpm_tracker = []
    total_done  = 0
    errors      = 0
    start_time  = time.monotonic()

    for batch_start in range(0, len(remaining), BATCH_SIZE):
        batch   = remaining[batch_start : batch_start + BATCH_SIZE]
        tasks   = [enrich_one(row, semaphore, rpm_tracker) for row in batch]
        results = await asyncio.gather(*tasks)

        bad     = [r for r in results if r["status"] != "ok"]
        errors += len(bad)

        append_results(results)
        save_checkpoint([str(r["review_id"]) for r in results])

        total_done += len(batch)
        elapsed     = time.monotonic() - start_time
        rate        = total_done / elapsed * 60  # records per minute
        remaining_n = len(remaining) - total_done
        eta_min     = remaining_n / rate if rate > 0 else 0

        print(
            f"Progress: {total_done}/{len(remaining)} "
            f"({total_done / len(remaining) * 100:.1f}%) | "
            f"rate: {rate:.0f} rpm | "
            f"ETA: {eta_min:.0f} min | "
            f"errors this batch: {len(bad)} | "
            f"total errors: {errors}"
        )

    elapsed_total = (time.monotonic() - start_time) / 60
    print(f"\nDone in {elapsed_total:.1f} min. Output: {OUTPUT_FILE}")
    print(f"Total errors: {errors}/{len(remaining)}")

if __name__ == "__main__":
    asyncio.run(main())