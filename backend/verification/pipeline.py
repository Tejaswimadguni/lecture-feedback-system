import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.paths import (
    get_results_dir,
    get_student_result_paths,
    validate_csv_file,
    validate_identifier,
)
from backend.retrival.vector_store import validate_and_load_knowledge_base
from backend.verification.claims import (
    extract_student_claims_to_file,
    load_and_validate_feedback_csv,
)
from backend.verification.evaluvator import evaluate_student_evidence_to_file
from backend.verification.retrieve_evidence import retrieve_student_evidence_to_file
from backend.verification.scorer import (
    load_lecture_concepts_for_scoring,
    save_all_students_summary,
    score_student_evaluated_to_file,
)


def run_verification_pipeline(
    course_id: str,
    lecture_id: str,
    feedback_csv: Union[str, Path],
    student_id_column: str = "roll_number",
    feedback_column: str = "feedback",
    top_k: int = 5,
    output_dir: Optional[Union[str, Path]] = None,
    data_root: Optional[Union[str, Path]] = None,
    strict_llm: bool = False,
) -> Dict[str, Any]:
    """
    Master dynamic pipeline runner for student feedback verification & evaluation.
    Strictly isolated to {course_id}/{lecture_id}:
      1. Validates identifiers, CSV structure/uniqueness, and isolated lecture Knowledge Base upfront.
      2. Claim Extraction -> {results_dir}/{student_id}/claims.json
      3. Evidence Retrieval (selected lecture KB only) -> {results_dir}/{student_id}/evidence.json
      4. Claim Evaluation -> {results_dir}/{student_id}/evaluated.json
      5. Dynamic Lecture-Specific Scoring -> {results_dir}/{student_id}/score.json
         + {results_dir}/all_students_summary.json
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")
    valid_csv = validate_csv_file(feedback_csv)

    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    # Pre-check 1: Validate that the exact selected lecture's knowledge base exists and is consistent
    loaded_kb = validate_and_load_knowledge_base(
        course_id=valid_course_id,
        lecture_id=valid_lecture_id,
        data_root=data_root,
    )

    # Pre-check 2: Validate feedback CSV columns, unique student IDs, and non-empty feedback
    student_entries = load_and_validate_feedback_csv(
        csv_path=valid_csv,
        student_id_column=student_id_column,
        feedback_column=feedback_column,
    )

    # Load lecture-specific concepts once for auditable dynamic coverage scoring
    lecture_concepts = load_lecture_concepts_for_scoring(
        course_id=valid_course_id,
        lecture_id=valid_lecture_id,
        data_root=data_root,
        loaded_kb=loaded_kb,
    )

    results_dir = get_results_dir(
        course_id=valid_course_id,
        lecture_id=valid_lecture_id,
        data_root=data_root,
        output_dir=output_dir,
    )
    results_dir.mkdir(parents=True, exist_ok=True)

    print("\n=========================================================", flush=True)
    print("      STUDENT FEEDBACK VERIFICATION PIPELINE             ", flush=True)
    print("=========================================================", flush=True)
    print(f" Course ID   : {valid_course_id}", flush=True)
    print(f" Lecture ID  : {valid_lecture_id}", flush=True)
    print(f" Feedback CSV: {valid_csv}", flush=True)
    print(f" Students    : {len(student_entries)}", flush=True)
    print(f" KB Chunks   : {len(loaded_kb[1])}", flush=True)
    print(f" Results Dir : {results_dir}\n", flush=True)

    student_paths_list = [
        (entry, get_student_result_paths(results_dir, entry["student_id"]))
        for entry in student_entries
    ]
    for _, spaths in student_paths_list:
        spaths.ensure_dir()

    # Step 1: Claim Extraction
    print("[STEP 1/4] Extracting student factual claims...", flush=True)
    for idx, (entry, spaths) in enumerate(student_paths_list, start=1):
        print(f"  [{idx}/{len(student_paths_list)}] Student '{entry['student_id']}' -> {spaths.claims}", flush=True)
        extract_student_claims_to_file(
            student_id=entry["student_id"],
            feedback=entry["feedback"],
            output_path=spaths.claims,
            course_id=valid_course_id,
            lecture_id=valid_lecture_id,
            strict_llm=strict_llm,
        )

    # Step 2: Evidence Retrieval (strictly isolated to selected lecture KB)
    print(
        f"\n[STEP 2/4] Retrieving lecture evidence from {valid_course_id}/{valid_lecture_id} knowledge base...",
        flush=True,
    )
    for idx, (entry, spaths) in enumerate(student_paths_list, start=1):
        print(f"  [{idx}/{len(student_paths_list)}] Student '{entry['student_id']}' -> {spaths.evidence}", flush=True)
        retrieve_student_evidence_to_file(
            claims_path=spaths.claims,
            output_path=spaths.evidence,
            course_id=valid_course_id,
            lecture_id=valid_lecture_id,
            top_k=top_k,
            data_root=data_root,
            loaded_kb=loaded_kb,
        )

    # Step 3: Claim Evaluation
    print("\n[STEP 3/4] Evaluating claims against retrieved lecture evidence...", flush=True)
    for idx, (entry, spaths) in enumerate(student_paths_list, start=1):
        print(f"  [{idx}/{len(student_paths_list)}] Student '{entry['student_id']}' -> {spaths.evaluated}", flush=True)
        evaluate_student_evidence_to_file(
            evidence_path=spaths.evidence,
            output_path=spaths.evaluated,
            course_id=valid_course_id,
            lecture_id=valid_lecture_id,
            strict_llm=strict_llm,
        )

    # Step 4: Dynamic Lecture-Specific Student Scoring
    print("\n[STEP 4/4] Computing final verification scores & lecture coverage metrics...", flush=True)
    scored_students: List[Dict[str, Any]] = []
    for idx, (entry, spaths) in enumerate(student_paths_list, start=1):
        scored = score_student_evaluated_to_file(
            evaluated_path=spaths.evaluated,
            output_path=spaths.score,
            course_id=valid_course_id,
            lecture_id=valid_lecture_id,
            lecture_concepts=lecture_concepts,
            data_root=data_root,
            loaded_kb=loaded_kb,
        )
        scored_students.append(scored)
        print(
            f"  [{idx}/{len(student_paths_list)}] Student '{entry['student_id']}': "
            f"Accuracy {scored['scores']['factual_accuracy']['score']}/5 | "
            f"Coverage {scored['scores']['lecture_coverage']['score']}/3 | "
            f"Understanding {scored['scores']['understanding_quality']['score']}/2 | "
            f"TOTAL {scored['scores']['total']['score']}/10",
            flush=True,
        )

    summary_path = results_dir / "all_students_summary.json"
    summary_payload = save_all_students_summary(
        scored_results=scored_students,
        course_id=valid_course_id,
        lecture_id=valid_lecture_id,
        summary_path=summary_path,
    )

    print("\n=========================================================", flush=True)
    print(" Verification Pipeline Execution Complete!               ", flush=True)
    print(f" Summary Saved: {summary_path}", flush=True)
    print("=========================================================\n", flush=True)

    return {
        "status": "success",
        "course_id": valid_course_id,
        "lecture_id": valid_lecture_id,
        "feedback_csv": str(valid_csv),
        "results_dir": str(results_dir),
        "summary_path": str(summary_path),
        "total_students": len(scored_students),
        "average_total_score": summary_payload["average_total_score"],
        "students": summary_payload["students"],
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dynamic Lecture-Isolated Student Feedback Verification Pipeline. "
            "Verifies student claims strictly against backend/data/lectures/{course_id}/{lecture_id}/knowledge_base/."
        )
    )
    parser.add_argument("--course-id", required=True, help="Explicit course identifier (required, e.g. DBMS).")
    parser.add_argument(
        "--lecture-id",
        required=True,
        help="Explicit lecture identifier (required, e.g. DBMS_lect1).",
    )
    parser.add_argument(
        "--feedback-csv",
        required=True,
        help="Explicit path to student feedback CSV file (required).",
    )
    parser.add_argument(
        "--student-id-column",
        default="roll_number",
        help="CSV column name for student identifier (default: roll_number).",
    )
    parser.add_argument(
        "--feedback-column",
        default="feedback",
        help="CSV column name for student feedback text (default: feedback).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of top evidence chunks retrieved per claim (default: 5).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional custom output directory (defaults to backend/data/results/{course_id}/{lecture_id}/).",
    )
    parser.add_argument(
        "--data-root",
        default=None,
        help="Optional custom data root directory (defaults to backend/data).",
    )
    parser.add_argument(
        "--strict-llm",
        action="store_true",
        help="Raise an error immediately if LLM API credentials are missing or an API request fails.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        run_verification_pipeline(
            course_id=args.course_id,
            lecture_id=args.lecture_id,
            feedback_csv=args.feedback_csv,
            student_id_column=args.student_id_column,
            feedback_column=args.feedback_column,
            top_k=args.top_k,
            output_dir=args.output_dir,
            data_root=args.data_root,
            strict_llm=args.strict_llm,
        )
    except Exception as e:
        logger.error(f"Verification pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
