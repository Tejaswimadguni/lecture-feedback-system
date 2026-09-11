import json
from pathlib import Path


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

EVALUATED_FILE = (
    PROJECT_ROOT
    / "data"
    / "results"
    / "student_01_evaluated.json"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "results"
    / "student_01_score.json"
)


# ============================================================
# SCORING WEIGHTS
# ============================================================

ACCURACY_MAX = 5
COVERAGE_MAX = 3
UNDERSTANDING_MAX = 2


# ============================================================
# CLAIM STATUS SCORES
# ============================================================

STATUS_SCORE = {
    "SUPPORTED": 1.0,
    "PARTIALLY_SUPPORTED": 0.5,
    "NOT_SUPPORTED": 0.0
}


# ============================================================
# LOAD EVALUATED DATA
# ============================================================

def load_evaluated_data():

    with open(
        EVALUATED_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


# ============================================================
# CALCULATE FACTUAL ACCURACY
# ============================================================

def calculate_accuracy(claims):

    if not claims:
        return 0.0

    total_score = 0.0

    for claim in claims:

        status = claim["status"]

        score = STATUS_SCORE.get(
            status,
            0.0
        )

        total_score += score

    maximum_score = len(claims)

    accuracy_score = (
        total_score / maximum_score
    ) * ACCURACY_MAX

    return round(
        accuracy_score,
        2
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n===================================")
    print("STUDENT SCORING")
    print("===================================")

    data = load_evaluated_data()

    roll_number = data["roll_number"]
    claims = data["claims"]

    print(
        f"\nStudent Roll Number: {roll_number}"
    )

    print(
        f"Total Claims: {len(claims)}"
    )

    # --------------------------------------------------------
    # Count claim statuses
    # --------------------------------------------------------

    supported = sum(
        1
        for claim in claims
        if claim["status"] == "SUPPORTED"
    )

    partially_supported = sum(
        1
        for claim in claims
        if claim["status"] == "PARTIALLY_SUPPORTED"
    )

    not_supported = sum(
        1
        for claim in claims
        if claim["status"] == "NOT_SUPPORTED"
    )

    # --------------------------------------------------------
    # Accuracy
    # --------------------------------------------------------

    accuracy_score = calculate_accuracy(
        claims
    )

    # --------------------------------------------------------
    # Coverage
    #
    # Not calculated yet.
    # We will implement this after defining
    # lecture-level concepts.
    # --------------------------------------------------------

    coverage_score = 0.0

    # --------------------------------------------------------
    # Understanding
    #
    # Not calculated yet.
    # We will implement this after deciding
    # how to measure explanation quality.
    # --------------------------------------------------------

    understanding_score = 0.0

    # --------------------------------------------------------
    # Total
    # --------------------------------------------------------

    total_score = (
        accuracy_score
        + coverage_score
        + understanding_score
    )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    output = {

        "roll_number": roll_number,

        "total_claims": len(claims),

        "claim_statistics": {

            "supported": supported,

            "partially_supported":
                partially_supported,

            "not_supported":
                not_supported
        },

        "scores": {

            "factual_accuracy": {
                "score": accuracy_score,
                "maximum": ACCURACY_MAX
            },

            "lecture_coverage": {
                "score": coverage_score,
                "maximum": COVERAGE_MAX
            },

            "understanding_quality": {
                "score": understanding_score,
                "maximum": UNDERSTANDING_MAX
            },

            "total": {
                "score": round(
                    total_score,
                    2
                ),
                "maximum": 10
            }
        }
    }

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

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
    # Print
    # --------------------------------------------------------

    print("\n-----------------------------------")
    print("CLAIM STATISTICS")
    print("-----------------------------------")

    print(
        f"Supported: {supported}"
    )

    print(
        f"Partially Supported: "
        f"{partially_supported}"
    )

    print(
        f"Not Supported: {not_supported}"
    )

    print("\n-----------------------------------")
    print("SCORE")
    print("-----------------------------------")

    print(
        f"Factual Accuracy: "
        f"{accuracy_score}/{ACCURACY_MAX}"
    )

    print(
        f"Lecture Coverage: "
        f"{coverage_score}/{COVERAGE_MAX}"
    )

    print(
        f"Understanding & Quality: "
        f"{understanding_score}/"
        f"{UNDERSTANDING_MAX}"
    )

    print(
        f"\nTOTAL: "
        f"{total_score}/10"
    )

    print(
        f"\nSaved to:\n{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()