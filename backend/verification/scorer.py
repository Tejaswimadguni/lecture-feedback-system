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
# CORE LECTURE TOPICS FOR COVERAGE METRIC
# ============================================================

CORE_LECTURE_TOPICS = {
    "course_expectations": ["expectation", "practice", "pset", "finger exercise", "office hours", "exam"],
    "computational_thinking": ["computational thinking", "computation", "problem solving"],
    "declarative_vs_imperative": ["declarative", "imperative", "recipe", "fact"],
    "algorithm_square_root": ["algorithm", "square root", "square-root", "guess", "checking", "improve", "stopping condition"],
    "computer_architecture": ["alu", "memory", "control unit", "instruction", "computer execution"],
    "stored_program_turing": ["turing", "stored program", "fixed program", "primitive operation"],
    "language_syntax_semantics": ["syntax", "static semantics", "semantics", "primitive construct"],
    "python_objects_types": ["object", "type", "int", "float", "bool", "nonetype", "scalar"],
    "expressions_operators": ["expression", "operator", "precedence", "casting", "conversion"],
    "variables_assignment_rebinding": ["variable", "assignment", "rebinding", "python tutor", "debugging"]
}


# ============================================================
# CALCULATE FACTUAL ACCURACY
# ============================================================

def calculate_accuracy(claims):
    if not claims:
        return 0.0

    total_score = 0.0
    for claim in claims:
        status = claim.get("status", "NOT_SUPPORTED")
        score = STATUS_SCORE.get(status, 0.0)
        total_score += score

    accuracy_score = (total_score / len(claims)) * ACCURACY_MAX
    return round(accuracy_score, 2)


# ============================================================
# CALCULATE LECTURE COVERAGE
# ============================================================

def calculate_coverage(claims):
    valid_claims = [c for c in claims if c.get("status") in ("SUPPORTED", "PARTIALLY_SUPPORTED")]
    if not valid_claims:
        return 0.0

    all_text = " ".join([c.get("claim", "").lower() for c in valid_claims])

    covered_topics = 0
    for topic, keywords in CORE_LECTURE_TOPICS.items():
        if any(kw in all_text for kw in keywords):
            covered_topics += 1

    coverage_score = (covered_topics / len(CORE_LECTURE_TOPICS)) * COVERAGE_MAX
    return round(coverage_score, 2)


# ============================================================
# CALCULATE UNDERSTANDING QUALITY
# ============================================================

def calculate_understanding(claims):
    if not claims:
        return 0.0

    supported_count = sum(1 for c in claims if c.get("status") == "SUPPORTED")
    partially_count = sum(1 for c in claims if c.get("status") == "PARTIALLY_SUPPORTED")
    total = len(claims)

    accuracy_ratio = (supported_count + 0.5 * partially_count) / total
    depth_ratio = min(1.0, total / 15.0)

    understanding_score = (0.6 * accuracy_ratio + 0.4 * depth_ratio) * UNDERSTANDING_MAX
    return round(understanding_score, 2)


# ============================================================
# SCORE SINGLE STUDENT DATA
# ============================================================

def score_student_data(data):
    roll_number = data.get("roll_number", 1)
    claims = data.get("claims", [])

    supported = sum(1 for claim in claims if claim.get("status") == "SUPPORTED")
    partially_supported = sum(1 for claim in claims if claim.get("status") == "PARTIALLY_SUPPORTED")
    not_supported = sum(1 for claim in claims if claim.get("status") == "NOT_SUPPORTED")

    accuracy_score = calculate_accuracy(claims)
    coverage_score = calculate_coverage(claims)
    understanding_score = calculate_understanding(claims)

    total_score = round(accuracy_score + coverage_score + understanding_score, 2)

    output = {
        "roll_number": roll_number,
        "total_claims": len(claims),
        "claim_statistics": {
            "supported": supported,
            "partially_supported": partially_supported,
            "not_supported": not_supported
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
                "score": total_score,
                "maximum": 10
            }
        }
    }
    return output


# ============================================================
# MAIN
# ============================================================

def main(target_roll_number=None):
    print("\n===================================")
    print("STUDENT SCORING")
    print("===================================")

    results_dir = OUTPUT_FILE.parent
    results_dir.mkdir(parents=True, exist_ok=True)

    if target_roll_number is not None:
        eval_files = [results_dir / f"student_{int(target_roll_number):02d}_evaluated.json"]
    else:
        eval_files = sorted(list(results_dir.glob("student_*_evaluated.json")))

    if not eval_files and EVALUATED_FILE.exists():
        eval_files = [EVALUATED_FILE]

    print(f"\nFound {len(eval_files)} evaluation files to score...")

    summary_list = []

    for idx, e_file in enumerate(eval_files, start=1):
        if not e_file.exists():
            continue

        with open(e_file, "r", encoding="utf-8") as f:
            d = json.load(f)

        res = score_student_data(d)
        roll_num = res["roll_number"]

        out_file = results_dir / f"student_{roll_num:02d}_score.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2, ensure_ascii=False)

        if roll_num == 1:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(res, f, indent=2, ensure_ascii=False)

        summary_list.append({
            "roll_number": roll_num,
            "total_claims": res["total_claims"],
            "supported": res["claim_statistics"]["supported"],
            "partially_supported": res["claim_statistics"]["partially_supported"],
            "not_supported": res["claim_statistics"]["not_supported"],
            "accuracy_score": res["scores"]["factual_accuracy"]["score"],
            "coverage_score": res["scores"]["lecture_coverage"]["score"],
            "understanding_score": res["scores"]["understanding_quality"]["score"],
            "total_score": res["scores"]["total"]["score"]
        })

        print(f"\n[{idx}/{len(eval_files)}] Roll No. {roll_num}: Accuracy: {res['scores']['factual_accuracy']['score']}/5 | Coverage: {res['scores']['lecture_coverage']['score']}/3 | Understanding: {res['scores']['understanding_quality']['score']}/2 | TOTAL: {res['scores']['total']['score']}/10")

    # Save summary for all students
    all_summary_path = results_dir / "all_students_summary.json"
    with open(all_summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_list, f, indent=2, ensure_ascii=False)

    print("\n===================================")
    print("SCORING COMPLETE")
    print(f"Scored {len(summary_list)} students. Saved summary to {all_summary_path}")
    print("===================================")


if __name__ == "__main__":
    main()