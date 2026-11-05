import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.paths import (
    get_results_dir,
    get_student_result_paths,
    sanitize_student_id,
    validate_csv_file,
    validate_identifier,
)
from backend.verification.llm_client import call_llm_json


def load_and_validate_feedback_csv(
    csv_path: Union[str, Path],
    student_id_column: str = "roll_number",
    feedback_column: str = "feedback",
) -> List[Dict[str, str]]:
    """
    Loads and strictly validates a student feedback CSV file:
      - Verifies file exists and is non-empty .csv
      - Verifies student_id_column and feedback_column exist in CSV headers
      - Verifies no missing/invalid/duplicate student IDs (both raw and sanitized)
      - Verifies no empty student feedback entries
    """
    valid_csv = validate_csv_file(csv_path)
    if not student_id_column or not student_id_column.strip():
        raise ValueError("student_id_column must be a non-empty column name.")
    if not feedback_column or not feedback_column.strip():
        raise ValueError("feedback_column must be a non-empty column name.")

    id_col = student_id_column.strip()
    fb_col = feedback_column.strip()

    with open(valid_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        if not fieldnames:
            raise ValueError(f"Feedback CSV '{valid_csv}' has no header row.")

        missing_cols = [col for col in (id_col, fb_col) if col not in fieldnames]
        if missing_cols:
            raise ValueError(
                f"Missing required CSV column(s) {missing_cols} in '{valid_csv.name}'. "
                f"Available columns: {fieldnames}"
            )

        rows = list(reader)

    if not rows:
        raise ValueError(f"Feedback CSV '{valid_csv.name}' contains no student rows.")

    validated_entries: List[Dict[str, str]] = []
    seen_raw_ids: set[str] = set()
    seen_sanitized_ids: Dict[str, str] = {}

    for row_idx, row in enumerate(rows, start=2):  # Row 1 is CSV header
        raw_id_val = row.get(id_col)
        if raw_id_val is None or not str(raw_id_val).strip():
            raise ValueError(
                f"Missing or empty student identifier in column '{id_col}' at CSV row {row_idx}."
            )

        raw_id = str(raw_id_val).strip()
        safe_id = sanitize_student_id(raw_id)

        if raw_id in seen_raw_ids:
            raise ValueError(
                f"Duplicate student identifier '{raw_id}' found at CSV row {row_idx}."
            )
        if safe_id in seen_sanitized_ids:
            prev_raw = seen_sanitized_ids[safe_id]
            raise ValueError(
                f"Student identifier collision at CSV row {row_idx}: '{raw_id}' and '{prev_raw}' "
                f"both map to sanitized directory '{safe_id}'."
            )

        raw_feedback = row.get(fb_col)
        if raw_feedback is None or not str(raw_feedback).strip():
            raise ValueError(
                f"Empty feedback for student '{raw_id}' in column '{fb_col}' at CSV row {row_idx}."
            )

        seen_raw_ids.add(raw_id)
        seen_sanitized_ids[safe_id] = raw_id
        validated_entries.append({
            "student_id": raw_id,
            "sanitized_id": safe_id,
            "feedback": str(raw_feedback).strip(),
        })

    return validated_entries


def fallback_extract_claims(feedback: str) -> Dict[str, Any]:
    """Deterministic sentence-level claim splitter used when LLM API is unavailable."""
    normalized = re.sub(r"\s+", " ", feedback.strip())
    raw_parts = re.split(r"(?<=[.!?;])\s+", normalized)
    sentences = [
        s.strip(" .!?;")
        for s in raw_parts
        if len(s.strip(" .!?;")) >= 8
    ]
    if not sentences and normalized:
        sentences = [normalized]

    claims = [
        {"claim_id": f"C{idx:02d}", "text": sentence}
        for idx, sentence in enumerate(sentences[:12], start=1)
    ]
    return {"claims": claims}


def extract_claims(feedback: str, strict_llm: bool = False) -> Dict[str, Any]:
    """
    Extracts atomic factual claims from a single student's feedback text.
    """
    if not isinstance(feedback, str) or not feedback.strip():
        raise ValueError("Student feedback cannot be empty for claim extraction.")

    clean_fb = feedback.strip()

    prompt = f"""You are analyzing a student's summary of a lecture.

Your task is to extract the key factual claims made by the student (up to 12 claims).

A factual claim is a statement that can be checked against the actual lecture material.

Rules:
1. Extract only factual claims about lecture content.
2. Do not add information that the student did not state.
3. Split compound statements into separate claims when useful.
4. Ignore greetings, pure opinions, feelings, and vague meta-statements.
5. Keep each claim concise and understandable on its own.
6. Return ONLY valid JSON without markdown formatting.

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
{clean_fb}
"""

    parsed = call_llm_json(prompt=prompt, max_tokens=600, strict_llm=strict_llm)
    if parsed is None:
        return fallback_extract_claims(clean_fb)

    raw_claims = parsed.get("claims")
    if not isinstance(raw_claims, list):
        if strict_llm:
            raise ValueError("LLM claim extraction response did not contain a valid 'claims' list.")
        return fallback_extract_claims(clean_fb)

    cleaned_claims: List[Dict[str, str]] = []
    for idx, item in enumerate(raw_claims, start=1):
        if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip():
            cleaned_claims.append({
                "claim_id": f"C{idx:02d}",
                "text": item["text"].strip(),
            })

    if not cleaned_claims:
        return fallback_extract_claims(clean_fb)

    return {"claims": cleaned_claims}


def extract_student_claims_to_file(
    student_id: str,
    feedback: str,
    output_path: Union[str, Path],
    course_id: str,
    lecture_id: str,
    strict_llm: bool = False,
) -> Dict[str, Any]:
    """
    Extracts claims for one student and saves explicitly to output_path (claims.json).
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")
    safe_id = sanitize_student_id(student_id)

    if not isinstance(feedback, str) or not feedback.strip():
        raise ValueError(f"Empty feedback for student '{student_id}'.")

    fb_hash = hashlib.sha256(feedback.strip().encode("utf-8")).hexdigest()
    dest = Path(output_path).resolve()

    result = extract_claims(feedback=feedback, strict_llm=strict_llm)
    claims = result.get("claims", [])

    payload = {
        "student_id": str(student_id).strip(),
        "sanitized_student_id": safe_id,
        "course_id": valid_course_id,
        "lecture_id": valid_lecture_id,
        "feedback_sha256": fb_hash,
        "total_claims": len(claims),
        "claims": claims,
    }

    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return payload


def run_claims_stage(
    course_id: str,
    lecture_id: str,
    feedback_csv: Union[str, Path],
    results_dir: Union[str, Path],
    student_id_column: str = "roll_number",
    feedback_column: str = "feedback",
    strict_llm: bool = False,
) -> List[Dict[str, Any]]:
    """
    Executes Step 1 (Claim Extraction) across all students in feedback_csv, writing each student's
    claims strictly to {results_dir}/{student_id}/claims.json.
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")
    entries = load_and_validate_feedback_csv(
        csv_path=feedback_csv,
        student_id_column=student_id_column,
        feedback_column=feedback_column,
    )

    out_root = Path(results_dir).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    outputs: List[Dict[str, Any]] = []
    for idx, entry in enumerate(entries, start=1):
        s_paths = get_student_result_paths(out_root, entry["student_id"])
        s_paths.ensure_dir()
        print(
            f"  [{idx}/{len(entries)}] Extracting claims for student '{entry['student_id']}'...",
            flush=True,
        )
        student_payload = extract_student_claims_to_file(
            student_id=entry["student_id"],
            feedback=entry["feedback"],
            output_path=s_paths.claims,
            course_id=valid_course_id,
            lecture_id=valid_lecture_id,
            strict_llm=strict_llm,
        )
        outputs.append(student_payload)

    return outputs


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Extract factual claims from student feedback CSV.")
    parser.add_argument("--course-id", required=True, help="Explicit course identifier.")
    parser.add_argument("--lecture-id", required=True, help="Explicit lecture identifier.")
    parser.add_argument("--feedback-csv", required=True, help="Path to student feedback CSV file.")
    parser.add_argument(
        "--student-id-column",
        default="roll_number",
        help="CSV column containing student identifiers (default: roll_number).",
    )
    parser.add_argument(
        "--feedback-column",
        default="feedback",
        help="CSV column containing feedback text (default: feedback).",
    )
    parser.add_argument("--output-dir", default=None, help="Optional explicit results directory.")
    parser.add_argument("--data-root", default=None, help="Optional custom data root directory.")
    parser.add_argument("--strict-llm", action="store_true", help="Fail immediately on LLM API errors.")

    args = parser.parse_args(argv)
    try:
        res_dir = get_results_dir(
            course_id=args.course_id,
            lecture_id=args.lecture_id,
            data_root=args.data_root,
            output_dir=args.output_dir,
        )
        outputs = run_claims_stage(
            course_id=args.course_id,
            lecture_id=args.lecture_id,
            feedback_csv=args.feedback_csv,
            results_dir=res_dir,
            student_id_column=args.student_id_column,
            feedback_column=args.feedback_column,
            strict_llm=args.strict_llm,
        )
        print(f"\nClaim extraction complete for {len(outputs)} students -> {res_dir}")
    except Exception as e:
        print(f"Error during claim extraction: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
