import csv
import json
import os
from pathlib import Path

# pyrefly: ignore [missing-import]
from google import genai


# --------------------------------------------------
# Project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CSV_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "students"
    / "lecture_feedback_25_students.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "results"
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "student_01_claims.json"
)


# --------------------------------------------------
# Gemini setup
# --------------------------------------------------

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError(
        "GEMINI_API_KEY is not set."
    )

client = genai.Client(
    api_key=api_key
)


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
# Extract claims using Gemini
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

    interaction = client.interactions.create(
        model="gemini-3.6-flash",
        input=prompt
    )

    response_text = interaction.output_text.strip()

    try:
        result = json.loads(response_text)

    except json.JSONDecodeError:

        # Handle accidental markdown fences
        if response_text.startswith("```"):

            response_text = (
                response_text
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )

            result = json.loads(response_text)

        else:
            raise ValueError(
                "Gemini did not return valid JSON.\n\n"
                + response_text
            )

    return result


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():

    roll_number = 1

    print("\n===================================")
    print("CLAIM EXTRACTION")
    print("===================================")

    print(
        f"\nLoading feedback for Roll No. {roll_number}..."
    )

    feedback = load_student_feedback(
        roll_number
    )

    print("\nStudent feedback:")
    print("-----------------------------------")
    print(feedback)

    print("\nExtracting claims using Gemini...")

    result = extract_claims(
        feedback
    )

    claims = result.get(
        "claims",
        []
    )

    print(
        f"\nClaims extracted: {len(claims)}"
    )

    print("\n-----------------------------------")

    for claim in claims:

        print(
            f"{claim['claim_id']}: "
            f"{claim['text']}"
        )

    # Create output directory
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # Save results
    output = {
        "roll_number": roll_number,
        "claims": claims
    }

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

    print("\nClaims saved to:")
    print(OUTPUT_FILE)

    print("\n===================================")
    print("CLAIM EXTRACTION COMPLETE")
    print("===================================")


if __name__ == "__main__":
    main()
