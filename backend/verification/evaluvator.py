import json
import os
from pathlib import Path

from google import genai


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
BATCH_SIZE = 4

# Number of evidence chunks given to Gemini for each claim
TOP_K_EVIDENCE = 5


# ============================================================
# LOAD EVIDENCE
# ============================================================

def load_evidence():
    with open(EVIDENCE_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


# ============================================================
# BUILD PROMPT FOR ONE BATCH
# ============================================================

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
- Do NOT assume something is true just because it sounds reasonable.
- Do NOT penalize the student for wording differences when the meaning
  is clearly supported.
- Base the decision on the evidence provided.
- Keep explanations concise.
- Return ONLY valid JSON.
- Do not include markdown code fences.

Required JSON format:

{
  "evaluations": [
    {
      "claim_id": "C01",
      "status": "SUPPORTED",
      "explanation": "Short explanation based on the evidence."
    }
  ]
}

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


# ============================================================
# EVALUATE ONE BATCH
# ============================================================

def evaluate_batch(batch):
    prompt = build_batch_prompt(batch)

    if openrouter_key and openrouter_key.startswith("sk-or-"):
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": MODEL_NAME,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}]
        }
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code != 200:
            raise ValueError(f"OpenRouter API error {res.status_code}: {res.text}")
        response_text = res.json()["choices"][0]["message"]["content"].strip()
    else:
        interaction = client.interactions.create(
            model="gemini-2.5-flash",
            input=prompt
        )
        response_text = interaction.output_text.strip()

    # Remove markdown fences if LLM accidentally adds them
    if response_text.startswith("```"):
        response_text = response_text.replace("```json", "")
        response_text = response_text.replace("```", "")
        response_text = response_text.strip()

    try:
        result = json.loads(response_text)

    except json.JSONDecodeError as error:
        print("\nLLM returned invalid JSON:")
        print(response_text)
        raise ValueError(
            "LLM response could not be parsed as JSON."
        ) from error

    return result["evaluations"]


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n===================================")
    print("CLAIM EVALUATION")
    print("===================================")

    data = load_evidence()

    roll_number = data["roll_number"]
    claims = data["claims"]

    print(f"\nStudent Roll Number: {roll_number}")
    print(f"Total Claims: {len(claims)}")
    print(f"Batch Size: {BATCH_SIZE}")
    print(f"Evidence per Claim: {TOP_K_EVIDENCE}")

    # --------------------------------------------------------
    # Prepare claims
    # --------------------------------------------------------

    prepared_claims = []

    for claim in claims:

        prepared_claims.append({
            "claim_id": claim["claim_id"],
            "claim_text": claim["claim"],
            "evidence": claim.get("evidence", [])
        })

    # --------------------------------------------------------
    # Split into batches
    # --------------------------------------------------------

    batches = [
        prepared_claims[i:i + BATCH_SIZE]
        for i in range(
            0,
            len(prepared_claims),
            BATCH_SIZE
        )
    ]

    print(f"\nTotal Gemini API calls required: {len(batches)}")

    # --------------------------------------------------------
    # Evaluate batches
    # --------------------------------------------------------

    all_evaluations = []

    for batch_number, batch in enumerate(
        batches,
        start=1
    ):

        print(
            f"\nEvaluating batch "
            f"{batch_number}/{len(batches)} "
            f"({len(batch)} claims)..."
        )

        evaluations = evaluate_batch(batch)

        all_evaluations.extend(evaluations)

        print(
            f"Batch {batch_number} completed."
        )

    # --------------------------------------------------------
    # Match evaluations to claims
    # --------------------------------------------------------

    evaluation_map = {
        item["claim_id"]: item
        for item in all_evaluations
    }

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

    # --------------------------------------------------------
    # Save result
    # --------------------------------------------------------

    output = {
        "roll_number": roll_number,
        "total_claims": len(final_claims),
        "claims": final_claims
    }

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False
        )

    # --------------------------------------------------------
    # Print summary
    # --------------------------------------------------------

    supported = sum(
        1
        for claim in final_claims
        if claim["status"] == "SUPPORTED"
    )

    partial = sum(
        1
        for claim in final_claims
        if claim["status"] == "PARTIALLY_SUPPORTED"
    )

    not_supported = sum(
        1
        for claim in final_claims
        if claim["status"] == "NOT_SUPPORTED"
    )

    print("\n===================================")
    print("EVALUATION COMPLETE")
    print("===================================")

    print(f"\nSupported: {supported}")
    print(f"Partially Supported: {partial}")
    print(f"Not Supported: {not_supported}")

    print(
        f"\nSaved to:\n{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()