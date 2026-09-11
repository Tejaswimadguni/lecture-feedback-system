import csv
import json
import os
from pathlib import Path

try:
    from google import genai
except ImportError:
    genai = None


# --------------------------------------------------
# Project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CSV_FILE_V2 = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "students"
    / "lecture_feedback_25_students_v2.csv"
)

CSV_FILE_V1 = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "students"
    / "lecture_feedback_25_students.csv"
)

CSV_FILE = CSV_FILE_V2 if CSV_FILE_V2.exists() else CSV_FILE_V1

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "results"
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "student_01_claims.json"
)


from dotenv import load_dotenv
import requests

load_dotenv()

openrouter_key = os.getenv("OPENROUTER_API_KEY")
gemini_key = os.getenv("GEMINI_API_KEY")

if not openrouter_key and not gemini_key:
    raise ValueError("Neither OPENROUTER_API_KEY nor GEMINI_API_KEY is set in .env")

if gemini_key and not openrouter_key:
    client = genai.Client(api_key=gemini_key)
else:
    client = None


# --------------------------------------------------
# Load one student's feedback
# --------------------------------------------------

def load_student_feedback(roll_number):

    with open(
        CSV_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:

            if str(row["roll_number"]).strip() == str(roll_number):

                return row["feedback"].strip()

    raise ValueError(
        f"Roll number {roll_number} not found."
    )


# --------------------------------------------------
# Extract claims using Gemini or OpenRouter
# --------------------------------------------------

def extract_claims(feedback):

    prompt = f"""
You are analyzing a student's summary of a lecture.

Your task is to extract the factual claims made by the student.

A factual claim is a statement that can be checked against
the actual lecture material.

Rules:
1. Extract only claims about lecture content.
2. Do not add information that the student did not state.
3. Split compound statements into separate claims when useful.
4. Ignore greetings, opinions, feelings, and vague statements.
5. Preserve the student's meaning.
6. Each claim should be understandable on its own.
7. Return ONLY valid JSON.
8. Do not include markdown or ```json fences.

Return exactly this structure:

{{
  "claims": [
    {{
      "claim_id": "C01",
      "text": "..."
    }}
  ]
}}

Student feedback:

{feedback}
"""

def repair_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Attempt to repair truncated JSON array by finding last closed object
        last_brace = text.rfind("}")
        if last_brace != -1:
            repaired = text[:last_brace+1]
            if not repaired.endswith("]}"):
                if not repaired.endswith("]"):
                    repaired += "]"
                repaired += "}"
            try:
                return json.loads(repaired)
            except Exception:
                pass
        raise


def fallback_extract_claims(feedback):
    sentences = [s.strip() for s in feedback.replace("\n", " ").split(".") if len(s.strip()) > 10]
    claims = []
    for idx, s in enumerate(sentences[:10], start=1):
        claims.append({"claim_id": f"C{idx:02d}", "text": s})
    return {"claims": claims}


API_CREDITS_EXHAUSTED = False

def extract_claims(feedback):
    global API_CREDITS_EXHAUSTED

    if API_CREDITS_EXHAUSTED:
        return fallback_extract_claims(feedback)

    prompt = f"""
You are analyzing a student's summary of a lecture.

Your task is to extract the 8 to 12 key factual claims made by the student.

A factual claim is a statement that can be checked against
the actual lecture material.

Rules:
1. Extract only main factual claims about lecture content.
2. Do not add information that the student did not state.
3. Keep claim descriptions concise (under 15 words each).
4. Ignore greetings, opinions, feelings, and vague statements.
5. Return ONLY valid JSON without markdown formatting.

Return exactly this structure:

{{
  "claims": [
    {{
      "claim_id": "C01",
      "text": "..."
    }}
  ]
}}

Student feedback:

{feedback}
"""

    if openrouter_key and openrouter_key.startswith("sk-or-"):
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "google/gemini-2.5-flash",
            "max_tokens": 120,
            "messages": [{"role": "user", "content": prompt}]
        }
        max_retries = 2
        res = None
        for attempt in range(max_retries):
            res = requests.post(url, headers=headers, json=payload)
            if res.status_code == 200:
                break
            if res.status_code == 402:
                print("  [Notice] OpenRouter free credits exhausted. Switching instantly to sentence extraction fallback.")
                API_CREDITS_EXHAUSTED = True
                return fallback_extract_claims(feedback)
            if res.status_code in (429, 503) and attempt < max_retries - 1:
                import time
                wait_sec = int(res.headers.get("Retry-After", 2 * (attempt + 1)))
                print(f"  [Rate limit {res.status_code}] Pausing for {wait_sec}s before retry...", flush=True)
                time.sleep(wait_sec)
        
        if res is None or res.status_code != 200:
            return fallback_extract_claims(feedback)

        response_text = res.json()["choices"][0]["message"]["content"].strip()
        import time
        time.sleep(0.5)
    else:
        interaction = client.interactions.create(
            model="gemini-2.5-flash",
            input=prompt
        )
        response_text = interaction.output_text.strip()

    try:
        result = repair_json(response_text)
    except Exception:
        return fallback_extract_claims(feedback)

    return result


# --------------------------------------------------
# Process Students Function
# --------------------------------------------------

def process_student(row):
    roll_number = int(row["roll_number"])
    out_file = OUTPUT_DIR / f"student_{roll_number:02d}_claims.json"
    if out_file.exists():
        try:
            with open(out_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if existing.get("claims"):
                    print(f"  --> Using cached claims for Roll No. {roll_number} ({len(existing['claims'])} claims).")
                    return existing
        except Exception:
            pass

    feedback = row["feedback"].strip()
    result = extract_claims(feedback)
    claims = result.get("claims", [])
    output = {
        "roll_number": roll_number,
        "claims": claims
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    if roll_number == 1:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

    return output


# --------------------------------------------------
# Main
# --------------------------------------------------

def main(target_roll_number=None):
    print("\n===================================")
    print("CLAIM EXTRACTION")
    print("===================================")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(CSV_FILE, "r", encoding="utf-8-sig", newline="") as file:
        reader = list(csv.DictReader(file))

    if target_roll_number is not None:
        target_rows = [r for r in reader if int(r["roll_number"]) == int(target_roll_number)]
    else:
        target_rows = reader

    print(f"\nProcessing {len(target_rows)} student feedback entries...")

    all_outputs = []
    for idx, row in enumerate(target_rows, start=1):
        roll_num = int(row["roll_number"])
        print(f"\n[{idx}/{len(target_rows)}] Extracting claims for Roll No. {roll_num}...")
        res = process_student(row)
        all_outputs.append(res)
        print(f"  --> Extracted {len(res['claims'])} claims.")

    # Save summary of all extracted claims
    all_file = OUTPUT_DIR / "all_students_claims.json"
    with open(all_file, "w", encoding="utf-8") as f:
        json.dump(all_outputs, f, indent=2, ensure_ascii=False)

    print("\n===================================")
    print("CLAIM EXTRACTION COMPLETE")
    print(f"Processed {len(all_outputs)} students. Saved to {OUTPUT_DIR}")
    print("===================================")


if __name__ == "__main__":
    main()

