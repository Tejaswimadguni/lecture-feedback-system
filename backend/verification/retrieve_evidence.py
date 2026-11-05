import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.paths import validate_identifier
from backend.retrival.search import search
from backend.retrival.vector_store import validate_and_load_knowledge_base


def retrieve_evidence(
    claims: List[Dict[str, Any]],
    course_id: str,
    lecture_id: str,
    top_k: int = 5,
    data_root: Optional[Union[str, Path]] = None,
    loaded_kb: Optional[Tuple[Any, List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieves Top-K lecture evidence chunks strictly from {course_id}/{lecture_id}'s
    isolated knowledge base for each student claim.
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    kb = (
        loaded_kb
        if loaded_kb is not None
        else validate_and_load_knowledge_base(
            course_id=valid_course_id,
            lecture_id=valid_lecture_id,
            data_root=data_root,
        )
    )

    results: List[Dict[str, Any]] = []
    for claim in claims:
        claim_id = claim["claim_id"]
        claim_text = claim["text"]

        search_hits = search(
            query=claim_text,
            course_id=valid_course_id,
            lecture_id=valid_lecture_id,
            top_k=top_k,
            data_root=data_root,
            loaded_kb=kb,
        )

        evidence_items: List[Dict[str, Any]] = []
        for hit in search_hits:
            if hit.get("course_id") != valid_course_id or hit.get("lecture_id") != valid_lecture_id:
                raise ValueError(
                    f"Evidence isolation violation: expected {valid_course_id}/{valid_lecture_id}, "
                    f"got {hit.get('course_id')}/{hit.get('lecture_id')}."
                )
            evidence_items.append({
                "score": hit["score"],
                "vector_id": hit["vector_id"],
                "course_id": hit["course_id"],
                "lecture_id": hit["lecture_id"],
                "chunk_id": hit["chunk_id"],
                "source_type": hit["source_type"],
                "source_file": hit["source_file"],
                "page": hit["page"],
                "start_time": hit["start_time"],
                "end_time": hit["end_time"],
                "text": hit["text"],
            })

        results.append({
            "claim_id": claim_id,
            "claim": claim_text,
            "evidence": evidence_items,
        })

    return results


def retrieve_student_evidence_to_file(
    claims_path: Union[str, Path],
    output_path: Union[str, Path],
    course_id: str,
    lecture_id: str,
    top_k: int = 5,
    data_root: Optional[Union[str, Path]] = None,
    loaded_kb: Optional[Tuple[Any, List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """
    Reads an explicit student claims.json file, retrieves evidence strictly from
    {course_id}/{lecture_id}'s knowledge base, and writes evidence.json to output_path.
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")

    src = Path(claims_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Claims file not found: {src}")

    with open(src, "r", encoding="utf-8") as f:
        claims_data = json.load(f)

    if (
        claims_data.get("course_id") != valid_course_id
        or claims_data.get("lecture_id") != valid_lecture_id
    ):
        raise ValueError(
            f"Claims file {src} belongs to {claims_data.get('course_id')}/{claims_data.get('lecture_id')}, "
            f"expected {valid_course_id}/{valid_lecture_id}."
        )

    student_id = claims_data["student_id"]
    claims_list = claims_data.get("claims", [])

    matched_claims = retrieve_evidence(
        claims=claims_list,
        course_id=valid_course_id,
        lecture_id=valid_lecture_id,
        top_k=top_k,
        data_root=data_root,
        loaded_kb=loaded_kb,
    )

    payload = {
        "student_id": student_id,
        "sanitized_student_id": claims_data.get("sanitized_student_id", student_id),
        "course_id": valid_course_id,
        "lecture_id": valid_lecture_id,
        "total_claims": len(matched_claims),
        "claims": matched_claims,
    }

    dest = Path(output_path).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return payload


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Retrieve lecture-isolated FAISS evidence for a student's extracted claims."
    )
    parser.add_argument("--course-id", required=True, help="Explicit course identifier.")
    parser.add_argument("--lecture-id", required=True, help="Explicit lecture identifier.")
    parser.add_argument("--claims-file", required=True, help="Explicit path to student claims.json.")
    parser.add_argument("--output-file", required=True, help="Explicit path to output evidence.json.")
    parser.add_argument("--top-k", type=int, default=5, help="Top-K chunks per claim (default: 5).")
    parser.add_argument("--data-root", default=None, help="Optional custom data root directory.")

    args = parser.parse_args(argv)
    try:
        retrieve_student_evidence_to_file(
            claims_path=args.claims_file,
            output_path=args.output_file,
            course_id=args.course_id,
            lecture_id=args.lecture_id,
            top_k=args.top_k,
            data_root=args.data_root,
        )
        print(f"Saved retrieved evidence to {args.output_file}")
    except Exception as e:
        print(f"Error during evidence retrieval: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
