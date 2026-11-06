import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.paths import get_lecture_paths, validate_identifier
from backend.processing.metadata import derive_lecture_concepts
from backend.retrival.vector_store import validate_and_load_knowledge_base

# ============================================================
# SCORING WEIGHTS (10-MARK RUBRIC)
# ============================================================

ACCURACY_MAX = 5
COVERAGE_MAX = 3
UNDERSTANDING_MAX = 2

STATUS_SCORE = {
    "SUPPORTED": 1.0,
    "PARTIALLY_SUPPORTED": 0.5,
    "NOT_SUPPORTED": 0.0,
}

# Letter grade bands applied to the total score out of 10 (inclusive lower bounds).
# Purely a presentation label: it does not alter the 5 / 3 / 2 rubric.
GRADE_BANDS = [
    (9.0, "A+"),
    (8.0, "A"),
    (7.0, "B"),
    (6.0, "C"),
    (5.0, "D"),
    (0.0, "F"),
]


def compute_grade(total_score: float) -> str:
    """Maps a total score (0-10) to its letter grade using GRADE_BANDS."""
    for lower_bound, label in GRADE_BANDS:
        if total_score >= lower_bound:
            return label
    return "F"


def load_lecture_concepts_for_scoring(
    course_id: str,
    lecture_id: str,
    data_root: Optional[Union[str, Path]] = None,
    loaded_kb: Optional[Tuple[Any, List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """
    Loads the lecture-specific concept units derived strictly from {course_id}/{lecture_id}.
    Reads metadata/dataset_metadata.json if present and verified for this lecture, otherwise
    computes deterministically from the lecture's validated chunk_mapping.json.
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")
    lpaths = get_lecture_paths(valid_course_id, valid_lecture_id, data_root=data_root)

    if loaded_kb is not None:
        _, mapping = loaded_kb
    else:
        _, mapping = validate_and_load_knowledge_base(
            course_id=valid_course_id,
            lecture_id=valid_lecture_id,
            data_root=data_root,
        )

    valid_chunk_ids = {entry["chunk_id"] for entry in mapping}

    if lpaths.dataset_metadata.exists():
        try:
            with open(lpaths.dataset_metadata, "r", encoding="utf-8") as f:
                meta = json.load(f)
            meta_concepts = meta.get("lecture_concepts")
            if (
                isinstance(meta, dict)
                and meta.get("course_id") == valid_course_id
                and meta.get("lecture_id") == valid_lecture_id
                and isinstance(meta_concepts, list)
                and len(meta_concepts) > 0
            ):
                # Ensure all referenced chunk_ids belong strictly to this lecture's current KB
                all_owned = all(
                    all(cid in valid_chunk_ids for cid in u.get("chunk_ids", []))
                    for u in meta_concepts
                )
                if all_owned:
                    return meta_concepts
        except Exception:
            pass

    return derive_lecture_concepts(mapping)


def calculate_accuracy(claims: List[Dict[str, Any]]) -> float:
    """Computes factual accuracy score out of 5 marks."""
    if not claims:
        return 0.0

    total_score = 0.0
    for claim in claims:
        status = claim.get("status", "NOT_SUPPORTED")
        total_score += STATUS_SCORE.get(status, 0.0)

    accuracy_score = (total_score / len(claims)) * ACCURACY_MAX
    return round(accuracy_score, 2)


def _keyword_present_in_text(keyword: str, normalized_text: str) -> bool:
    pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
    return bool(re.search(pattern, normalized_text))


def calculate_coverage(
    claims: List[Dict[str, Any]],
    lecture_concepts: List[Dict[str, Any]],
    course_id: str,
    lecture_id: str,
) -> Tuple[float, Dict[str, Any]]:
    """
    Evaluates Lecture Coverage (out of 3 marks) strictly against the selected lecture's
    derived concept units and supporting lecture chunk references.
    """
    valid_claims = [
        c for c in claims if c.get("status") in ("SUPPORTED", "PARTIALLY_SUPPORTED")
    ]
    total_units = len(lecture_concepts)

    if not valid_claims or total_units == 0:
        return 0.0, {
            "course_id": course_id,
            "lecture_id": lecture_id,
            "total_lecture_units": total_units,
            "covered_lecture_units": 0,
            "evidenced_chunk_ids": [],
            "covered_units": [],
            "uncovered_units": [
                {"unit_id": u["unit_id"], "label": u["label"]} for u in lecture_concepts
            ],
        }

    # Collect lecture chunk IDs directly cited as top supporting evidence for valid claims
    evidenced_chunk_ids: set[str] = set()
    for claim in valid_claims:
        ev_list = claim.get("evidence", [])
        if ev_list:
            # Primary supporting chunk for the verified claim
            top_ev = ev_list[0]
            if (
                top_ev.get("course_id") == course_id
                and top_ev.get("lecture_id") == lecture_id
                and top_ev.get("chunk_id")
            ):
                evidenced_chunk_ids.add(top_ev["chunk_id"])

    all_valid_text = " ".join(c.get("claim", "").lower() for c in valid_claims)

    covered_units: List[Dict[str, Any]] = []
    uncovered_units: List[Dict[str, Any]] = []

    for unit in lecture_concepts:
        unit_chunk_ids = unit.get("chunk_ids", [])
        unit_keywords = unit.get("keywords", [])

        matched_chunks = [cid for cid in unit_chunk_ids if cid in evidenced_chunk_ids]
        matched_kws = [kw for kw in unit_keywords if _keyword_present_in_text(kw, all_valid_text)]

        # A lecture unit is covered if supported claims directly cite chunks from this unit
        # or explicitly cover its distinctive domain concepts (bigram or >=2 domain terms, or 1 if unit has <=2 terms)
        has_bigram_match = any(" " in kw for kw in matched_kws)
        min_kw_required = 1 if len(unit_keywords) <= 2 else 2
        covered_by_concepts = has_bigram_match or len(matched_kws) >= min_kw_required

        if matched_chunks or covered_by_concepts:
            covered_units.append({
                "unit_id": unit["unit_id"],
                "label": unit["label"],
                "matched_chunk_ids": matched_chunks,
                "matched_keywords": matched_kws,
            })
        else:
            uncovered_units.append({
                "unit_id": unit["unit_id"],
                "label": unit["label"],
            })

    coverage_score = round((len(covered_units) / total_units) * COVERAGE_MAX, 2)
    details = {
        "course_id": course_id,
        "lecture_id": lecture_id,
        "total_lecture_units": total_units,
        "covered_lecture_units": len(covered_units),
        "evidenced_chunk_ids": sorted(evidenced_chunk_ids),
        "covered_units": covered_units,
        "uncovered_units": uncovered_units,
    }
    return coverage_score, details


def calculate_understanding(claims: List[Dict[str, Any]]) -> float:
    """Computes understanding quality score out of 2 marks."""
    if not claims:
        return 0.0

    supported_count = sum(1 for c in claims if c.get("status") == "SUPPORTED")
    partially_count = sum(1 for c in claims if c.get("status") == "PARTIALLY_SUPPORTED")
    effective_valid = supported_count + 0.5 * partially_count

    if effective_valid <= 0.0:
        return 0.0

    total = len(claims)
    accuracy_ratio = effective_valid / total
    depth_ratio = min(1.0, effective_valid / 10.0)

    understanding_score = (0.6 * accuracy_ratio + 0.4 * depth_ratio) * UNDERSTANDING_MAX
    return round(understanding_score, 2)


def score_student_data(
    evaluated_data: Dict[str, Any],
    lecture_concepts: List[Dict[str, Any]],
    course_id: str,
    lecture_id: str,
) -> Dict[str, Any]:
    """
    Computes auditable multi-factor scores for one student strictly against {course_id}/{lecture_id}.
    Preserves evaluated claims, explanations, and lecture evidence references.
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")

    if (
        evaluated_data.get("course_id") != valid_course_id
        or evaluated_data.get("lecture_id") != valid_lecture_id
    ):
        raise ValueError(
            f"Evaluated data belongs to {evaluated_data.get('course_id')}/{evaluated_data.get('lecture_id')}, "
            f"expected {valid_course_id}/{valid_lecture_id}."
        )

    student_id = evaluated_data["student_id"]
    claims = evaluated_data.get("claims", [])

    supported = sum(1 for c in claims if c.get("status") == "SUPPORTED")
    partially_supported = sum(1 for c in claims if c.get("status") == "PARTIALLY_SUPPORTED")
    not_supported = sum(1 for c in claims if c.get("status") == "NOT_SUPPORTED")

    accuracy_score = calculate_accuracy(claims)
    coverage_score, coverage_details = calculate_coverage(
        claims=claims,
        lecture_concepts=lecture_concepts,
        course_id=valid_course_id,
        lecture_id=valid_lecture_id,
    )
    understanding_score = calculate_understanding(claims)

    total_score = round(accuracy_score + coverage_score + understanding_score, 2)

    return {
        "student_id": student_id,
        "sanitized_student_id": evaluated_data.get("sanitized_student_id", student_id),
        "course_id": valid_course_id,
        "lecture_id": valid_lecture_id,
        "total_claims": len(claims),
        "claim_statistics": {
            "supported": supported,
            "partially_supported": partially_supported,
            "not_supported": not_supported,
        },
        "scores": {
            "factual_accuracy": {
                "score": accuracy_score,
                "maximum": ACCURACY_MAX,
            },
            "lecture_coverage": {
                "score": coverage_score,
                "maximum": COVERAGE_MAX,
            },
            "understanding_quality": {
                "score": understanding_score,
                "maximum": UNDERSTANDING_MAX,
            },
            "total": {
                "score": total_score,
                "maximum": ACCURACY_MAX + COVERAGE_MAX + UNDERSTANDING_MAX,
            },
        },
        "grade": compute_grade(total_score),
        "coverage_details": coverage_details,
        "evaluated_claims": claims,
    }


def score_student_evaluated_to_file(
    evaluated_path: Union[str, Path],
    output_path: Union[str, Path],
    course_id: str,
    lecture_id: str,
    lecture_concepts: Optional[List[Dict[str, Any]]] = None,
    data_root: Optional[Union[str, Path]] = None,
    loaded_kb: Optional[Tuple[Any, List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """
    Scores an explicit student evaluated.json file and writes score.json to output_path.
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")

    src = Path(evaluated_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Evaluated claims file not found: {src}")

    with open(src, "r", encoding="utf-8") as f:
        evaluated_data = json.load(f)

    concepts = (
        lecture_concepts
        if lecture_concepts is not None
        else load_lecture_concepts_for_scoring(
            course_id=valid_course_id,
            lecture_id=valid_lecture_id,
            data_root=data_root,
            loaded_kb=loaded_kb,
        )
    )

    scored = score_student_data(
        evaluated_data=evaluated_data,
        lecture_concepts=concepts,
        course_id=valid_course_id,
        lecture_id=valid_lecture_id,
    )

    dest = Path(output_path).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(scored, f, indent=2, ensure_ascii=False)

    return scored


def save_all_students_summary(
    scored_results: List[Dict[str, Any]],
    course_id: str,
    lecture_id: str,
    summary_path: Union[str, Path],
) -> Dict[str, Any]:
    """Saves the lecture-level summary file all_students_summary.json."""
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")

    students_table: List[Dict[str, Any]] = []
    for res in scored_results:
        students_table.append({
            "student_id": res["student_id"],
            "sanitized_student_id": res["sanitized_student_id"],
            "total_claims": res["total_claims"],
            "supported": res["claim_statistics"]["supported"],
            "partially_supported": res["claim_statistics"]["partially_supported"],
            "not_supported": res["claim_statistics"]["not_supported"],
            "accuracy_score": res["scores"]["factual_accuracy"]["score"],
            "coverage_score": res["scores"]["lecture_coverage"]["score"],
            "understanding_score": res["scores"]["understanding_quality"]["score"],
            "total_score": res["scores"]["total"]["score"],
            "grade": res.get("grade") or compute_grade(res["scores"]["total"]["score"]),
        })

    avg_total = (
        round(sum(s["total_score"] for s in students_table) / len(students_table), 2)
        if students_table
        else 0.0
    )

    summary_payload = {
        "course_id": valid_course_id,
        "lecture_id": valid_lecture_id,
        "total_students": len(students_table),
        "average_total_score": avg_total,
        "students": students_table,
    }

    dest = Path(summary_path).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2, ensure_ascii=False)

    return summary_payload


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Compute lecture-specific student verification scores from evaluated.json."
    )
    parser.add_argument("--course-id", required=True, help="Explicit course identifier.")
    parser.add_argument("--lecture-id", required=True, help="Explicit lecture identifier.")
    parser.add_argument("--evaluated-file", required=True, help="Explicit path to student evaluated.json.")
    parser.add_argument("--output-file", required=True, help="Explicit path to output score.json.")
    parser.add_argument("--data-root", default=None, help="Optional custom data root directory.")

    args = parser.parse_args(argv)
    try:
        res = score_student_evaluated_to_file(
            evaluated_path=args.evaluated_file,
            output_path=args.output_file,
            course_id=args.course_id,
            lecture_id=args.lecture_id,
            data_root=args.data_root,
        )
        print(
            f"Scored student '{res['student_id']}' ({args.course_id}/{args.lecture_id}): "
            f"Total {res['scores']['total']['score']}/10 -> {args.output_file}"
        )
    except Exception as e:
        print(f"Error during student scoring: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
