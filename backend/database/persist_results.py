import csv
import json
from pathlib import Path

from database import get_connection
from repository import (
    save_student,
    save_submission,
    save_claim,
    save_evidence,
    save_evaluation,
    save_score,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

RESULTS_DIR = (
    PROJECT_ROOT
    / "data"
    / "results"
)

STUDENT_CSV = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "students"
    / "lecture_feedback_25_students_v2.csv"
)

if not STUDENT_CSV.exists():
    STUDENT_CSV = (
        PROJECT_ROOT
        / "data"
        / "raw"
        / "students"
        / "lecture_feedback_25_students.csv"
    )


def load_json(file_path):
    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)


def get_student_feedback(roll_number):
    with open(
        STUDENT_CSV,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:

            if (
                str(row["roll_number"]).strip()
                == str(roll_number)
            ):
                return row["feedback"].strip()

    raise ValueError(
        f"Roll number {roll_number} not found in student CSV."
    )


def find_student_roll_numbers():
    roll_numbers = []

    for claims_file in RESULTS_DIR.glob(
        "student_*_claims.json"
    ):

        data = load_json(claims_file)

        roll_number = data.get("roll_number")

        if roll_number is not None:
            roll_numbers.append(
                int(roll_number)
            )

    return sorted(set(roll_numbers))


def persist_student(
    roll_number,
    lecture_id="6100l-lecture-1-version-2_360p_16_9"
):
    print("\n===================================")
    print(
        f"PERSISTING ROLL NO. {roll_number}"
    )
    print("===================================")

    claims_file = (
        RESULTS_DIR
        / f"student_{roll_number:02d}_claims.json"
    )

    evidence_file = (
        RESULTS_DIR
        / f"student_{roll_number:02d}_evidence.json"
    )

    evaluated_file = (
        RESULTS_DIR
        / f"student_{roll_number:02d}_evaluated.json"
    )

    score_file = (
        RESULTS_DIR
        / f"student_{roll_number:02d}_score.json"
    )

    required_files = [
        claims_file,
        evidence_file,
        evaluated_file,
        score_file,
    ]

    for file_path in required_files:

        if not file_path.exists():
            raise FileNotFoundError(
                f"Required result file not found: "
                f"{file_path}"
            )

    claims_data = load_json(
        claims_file
    )

    evidence_data = load_json(
        evidence_file
    )

    evaluated_data = load_json(
        evaluated_file
    )

    score_data = load_json(
        score_file
    )

    feedback = get_student_feedback(
        roll_number
    )

    student_id = save_student(
        roll_number
    )

    print(
        f"✅ Student saved: DB ID {student_id}"
    )

    submission_id = save_submission(
        student_id=student_id,
        lecture_id=lecture_id,
        feedback_text=feedback,
    )

    print(
        f"✅ Submission saved: DB ID {submission_id}"
    )

    evidence_by_claim = {
        item["claim_id"]: item
        for item in evidence_data.get(
            "claims",
            []
        )
    }

    evaluations_by_claim = {
        item["claim_id"]: item
        for item in evaluated_data.get(
            "claims",
            []
        )
    }

    for claim in claims_data.get(
        "claims",
        []
    ):

        claim_id = claim["claim_id"]

        db_claim_id = save_claim(
            submission_id,
            {
                "claim_id": claim_id,
                "text": claim["text"],
            }
        )

        print(
            f"   ✅ Claim {claim_id} saved"
        )

        evidence_group = (
            evidence_by_claim.get(
                claim_id,
                {}
            )
        )

        for evidence in evidence_group.get(
            "evidence",
            []
        ):

            save_evidence(
                db_claim_id,
                evidence
            )

        evaluation = (
            evaluations_by_claim.get(
                claim_id
            )
        )

        if evaluation:

            save_evaluation(
                claim_db_id=db_claim_id,
                status=evaluation.get(
                    "status"
                ),
                reasoning=evaluation.get(
                    "explanation"
                ),
            )

    scores = score_data.get(
        "scores",
        {}
    )

    factual_accuracy = (
        scores
        .get("factual_accuracy", {})
        .get("score", 0)
    )

    lecture_coverage = (
        scores
        .get("lecture_coverage", {})
        .get("score", 0)
    )

    understanding_quality = (
        scores
        .get("understanding_quality", {})
        .get("score", 0)
    )

    total_score = (
        scores
        .get("total", {})
        .get("score", 0)
    )

    score_id = save_score(
        submission_id=submission_id,
        factual_accuracy=factual_accuracy,
        lecture_coverage=lecture_coverage,
        understanding_quality=understanding_quality,
        total_score=total_score,
    )

    print(
        f"✅ Score saved: DB ID {score_id}"
    )

    print(
        f"   Claims: {len(claims_data.get('claims', []))}"
    )

    print(
        f"   Final Score: {total_score}/10"
    )


def main():

    print("\n===================================")
    print("STUDENT DATABASE PERSISTENCE")
    print("===================================")

    roll_numbers = (
        find_student_roll_numbers()
    )

    if not roll_numbers:

        print(
            "❌ No student result files found."
        )

        return

    print(
        f"\nFound {len(roll_numbers)} students."
    )

    for roll_number in roll_numbers:

        try:

            persist_student(
                roll_number
            )

        except Exception as error:

            print(
                f"\n❌ Failed for roll number "
                f"{roll_number}:"
            )

            print(error)

    print("\n===================================")
    print("ALL STUDENTS PROCESSED")
    print("===================================")


if __name__ == "__main__":
    main()