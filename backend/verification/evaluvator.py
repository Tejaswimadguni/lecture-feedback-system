import json
import os
from pathlib import Path

try:
    from google import genai
except ImportError:
    genai = None


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

EVIDENCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "results"
    / "student_01_evidence.json"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "results"
    / "student_01_evaluated.json"
)


# ============================================================
# LLM SETUP (OpenRouter / Gemini)
# ============================================================

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

MODEL_NAME = "google/gemini-2.5-flash"



# ============================================================
# SETTINGS
# ============================================================

# Number of claims evaluated in one Gemini request
BATCH_SIZE = 2

# Number of evidence chunks given to Gemini for each claim
TOP_K_EVIDENCE = 3


def fallback_batch_eval(batch):
    evals = []
    for claim in batch:
        c_id = claim.get("claim_id")
        ev = claim.get("evidence", [])
        top_score = ev[0].get("score", 0.0) if ev else 0.0
        if top_score >= 0.60:
            st = "SUPPORTED"
            exp = f"Evidence strongly matches claim (vector similarity {top_score:.2f})."
        elif top_score >= 0.45:
            st = "PARTIALLY_SUPPORTED"
            exp = f"Evidence partially matches claim (vector similarity {top_score:.2f})."
        else:
            st = "NOT_SUPPORTED"
            exp = f"Evidence does not sufficiently support claim (similarity {top_score:.2f})."
        evals.append({"claim_id": c_id, "status": st, "explanation": exp})
    return evals


def build_batch_prompt(batch):
    prompt = """
You are evaluating factual claims made by a student about a lecture.

For each claim, compare the student's claim against the retrieved
lecture evidence.

Use ONLY the provided evidence.

Classify each claim as exactly one of:

SUPPORTED
PARTIALLY_SUPPORTED
NOT_SUPPORTED

Definitions:

SUPPORTED:
The lecture evidence clearly supports the student's claim.

PARTIALLY_SUPPORTED:
The evidence supports only part of the claim, or the student's
claim contains some supported information and some unsupported
information.

NOT_SUPPORTED:
The provided evidence does not support the claim.

Important:
- Do NOT use outside knowledge.
- Base the decision on the evidence provided.
- Keep explanations concise.
- Return ONLY valid JSON: {"evaluations": [{"claim_id": "C01", "status": "SUPPORTED", "explanation": "..."}]}

Here are the claims and their lecture evidence:

"""

    for claim in batch:
        prompt += "\n========================================\n"
        prompt += f"CLAIM ID: {claim['claim_id']}\n"
        prompt += f"STUDENT CLAIM: {claim['claim_text']}\n"
        prompt += "\nLECTURE EVIDENCE:\n"

        evidence = claim.get("evidence", [])

        for i, item in enumerate(
            evidence[:TOP_K_EVIDENCE],
            start=1
        ):
            prompt += f"\nEvidence {i}:\n"
            prompt += f"Source: {item.get('source_type')}\n"

            if item.get("page") is not None:
                prompt += f"Page: {item.get('page')}\n"

            if item.get("start_time") is not None:
                prompt += (
                    f"Time: {item.get('start_time')} - "
                    f"{item.get('end_time')}\n"
                )

            prompt += f"Similarity: {item.get('score')}\n"
            prompt += f"Text: {item.get('text')}\n"

    return prompt


API_CREDITS_EXHAUSTED = False

def evaluate_batch(batch):
    global API_CREDITS_EXHAUSTED

    if API_CREDITS_EXHAUSTED:
        return fallback_batch_eval(batch)

    prompt = build_batch_prompt(batch)

    if openrouter_key and openrouter_key.startswith("sk-or-"):
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": MODEL_NAME,
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
                print("  [Notice] OpenRouter free credits exhausted. Switching instantly to similarity scoring fallback.")
                API_CREDITS_EXHAUSTED = True
                return fallback_batch_eval(batch)
            if res.status_code in (429, 503) and attempt < max_retries - 1:
                import time
                wait_sec = int(res.headers.get("Retry-After", 2 * (attempt + 1)))
                print(f"  [Rate limit {res.status_code}] Pausing for {wait_sec}s before retry...", flush=True)
                time.sleep(wait_sec)
        
        if res is None or res.status_code != 200:
            return fallback_batch_eval(batch)

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
        return fallback_batch_eval(batch)

    return result.get("evaluations", [])


# ============================================================
# EVALUATE SINGLE STUDENT FILE
# ============================================================

def evaluate_student_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    roll_number = data.get("roll_number", 1)
    out_file = file_path.parent / f"student_{roll_number:02d}_evaluated.json"
    if out_file.exists():
        try:
            with open(out_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if existing.get("claims"):
                    print(f"  --> Using cached evaluations for Roll No. {roll_number} ({len(existing['claims'])} claims).")
                    return existing
        except Exception:
            pass
    claims = data.get("claims", [])

    prepared_claims = []
    for claim in claims:
        prepared_claims.append({
            "claim_id": claim["claim_id"],
            "claim_text": claim["claim"],
            "evidence": claim.get("evidence", [])
        })

    batches = [
        prepared_claims[i:i + BATCH_SIZE]
        for i in range(0, len(prepared_claims), BATCH_SIZE)
    ]

    all_evaluations = []
    for batch in batches:
        evaluations = evaluate_batch(batch)
        all_evaluations.extend(evaluations)

    evaluation_map = {item["claim_id"]: item for item in all_evaluations}

    final_claims = []
    for claim in claims:
        claim_id = claim["claim_id"]
        evaluation = evaluation_map.get(
            claim_id,
            {
                "claim_id": claim_id,
                "status": "NOT_SUPPORTED",
                "explanation": "No evaluation returned."
            }
        )
        final_claims.append({
            "claim_id": claim_id,
            "claim": claim["claim"],
            "status": evaluation["status"],
            "explanation": evaluation["explanation"],
            "evidence": claim.get("evidence", [])[:TOP_K_EVIDENCE]
        })

    output = {
        "roll_number": roll_number,
        "total_claims": len(final_claims),
        "claims": final_claims
    }

    out_file = file_path.parent / f"student_{roll_number:02d}_evaluated.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    if roll_number == 1:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

    return output


# ============================================================
# MAIN
# ============================================================

def main(target_roll_number=None):
    print("\n===================================")
    print("CLAIM EVALUATION")
    print("===================================")

    results_dir = OUTPUT_FILE.parent
    results_dir.mkdir(parents=True, exist_ok=True)

    if target_roll_number is not None:
        evidence_files = [results_dir / f"student_{int(target_roll_number):02d}_evidence.json"]
    else:
        evidence_files = sorted(list(results_dir.glob("student_*_evidence.json")))

    if not evidence_files and EVIDENCE_FILE.exists():
        evidence_files = [EVIDENCE_FILE]

    print(f"\nFound {len(evidence_files)} evidence files to evaluate...")

    for idx, e_file in enumerate(evidence_files, start=1):
        if not e_file.exists():
            continue

        with open(e_file, "r", encoding="utf-8") as f:
            d = json.load(f)

        roll_num = d.get("roll_number", idx)
        print(f"\n[{idx}/{len(evidence_files)}] Evaluating Roll No. {roll_num} ({len(d.get('claims', []))} claims)...")
        res = evaluate_student_file(e_file)

        supported = sum(1 for c in res["claims"] if c["status"] == "SUPPORTED")
        partially = sum(1 for c in res["claims"] if c["status"] == "PARTIALLY_SUPPORTED")
        unsupported = sum(1 for c in res["claims"] if c["status"] == "NOT_SUPPORTED")
        print(f"  --> Supported: {supported} | Partial: {partially} | Not Supported: {unsupported}")

    print("\n===================================")
    print("EVALUATION COMPLETE")
    print(f"Evaluated {len(evidence_files)} students. Saved to {results_dir}")
    print("===================================")


if __name__ == "__main__":
    main()