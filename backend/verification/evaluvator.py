import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.paths import validate_identifier
from backend.verification.llm_client import call_llm_json

BATCH_SIZE = 4
TOP_K_EVIDENCE = 3
VALID_STATUSES = {"SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED"}


def fallback_batch_eval(batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deterministic evidence-similarity evaluator used when LLM API is unavailable.
    Evaluates strictly against the retrieved lecture evidence scores.
    """
    evals: List[Dict[str, Any]] = []
    for claim in batch:
        c_id = claim.get("claim_id")
        ev = claim.get("evidence", [])
        top_score = float(ev[0].get("score", 0.0)) if ev else 0.0
        top_chunk = ev[0].get("chunk_id", "none") if ev else "none"

        if top_score >= 0.55:
            status = "SUPPORTED"
            exp = (
                f"Retrieved lecture chunk '{top_chunk}' strongly supports this claim "
                f"(cosine similarity {top_score:.2f})."
            )
        elif top_score >= 0.40:
            status = "PARTIALLY_SUPPORTED"
            exp = (
                f"Retrieved lecture chunk '{top_chunk}' partially aligns with this claim "
                f"(cosine similarity {top_score:.2f})."
            )
        else:
            status = "NOT_SUPPORTED"
            exp = (
                f"Retrieved lecture evidence does not sufficiently support this claim "
                f"(highest similarity {top_score:.2f})."
            )

        evals.append({
            "claim_id": c_id,
            "status": status,
            "explanation": exp,
        })
    return evals


def build_batch_prompt(batch: List[Dict[str, Any]]) -> str:
    prompt = """You are evaluating factual claims made by a student about a specific lecture.

For each claim, compare the student's claim strictly against the retrieved lecture evidence below.
Use ONLY the provided lecture evidence. Do NOT use outside knowledge.

Classify each claim as exactly one of:
- SUPPORTED: The lecture evidence clearly supports the student's claim.
- PARTIALLY_SUPPORTED: The evidence supports only part of the claim, or mixes supported and unsupported details.
- NOT_SUPPORTED: The provided lecture evidence does not support the claim or contradicts it.

Return ONLY valid JSON with this structure:
{"evaluations": [{"claim_id": "C01", "status": "SUPPORTED", "explanation": "Concise reason citing evidence."}]}

Claims and retrieved lecture evidence:
"""
    for claim in batch:
        prompt += "\n========================================\n"
        prompt += f"CLAIM ID: {claim['claim_id']}\n"
        prompt += f"STUDENT CLAIM: {claim['claim_text']}\n"
        prompt += "\nLECTURE EVIDENCE:\n"

        evidence = claim.get("evidence", [])
        for i, item in enumerate(evidence[:TOP_K_EVIDENCE], start=1):
            prompt += f"\nEvidence {i} (Chunk {item.get('chunk_id')}):\n"
            prompt += f"Source: {item.get('source_type')} ({item.get('source_file')})\n"
            if item.get("page") is not None:
                prompt += f"Page: {item.get('page')}\n"
            if item.get("start_time") is not None:
                prompt += f"Time: {item.get('start_time')} - {item.get('end_time')}\n"
            prompt += f"Similarity: {item.get('score')}\n"
            prompt += f"Text: {item.get('text')}\n"

    return prompt


def evaluate_batch(batch: List[Dict[str, Any]], strict_llm: bool = False) -> List[Dict[str, Any]]:
    prompt = build_batch_prompt(batch)
    parsed = call_llm_json(prompt=prompt, max_tokens=700, strict_llm=strict_llm)
    if parsed is None:
        return fallback_batch_eval(batch)

    raw_evals = parsed.get("evaluations")
    if not isinstance(raw_evals, list):
        if strict_llm:
            raise ValueError("LLM evaluation response missing 'evaluations' list.")
        return fallback_batch_eval(batch)

    normalized: List[Dict[str, Any]] = []
    for item in raw_evals:
        if not isinstance(item, dict) or not item.get("claim_id"):
            continue
        raw_status = str(item.get("status", "NOT_SUPPORTED")).strip().upper()
        status = raw_status if raw_status in VALID_STATUSES else "NOT_SUPPORTED"
        explanation = str(item.get("explanation", "")).strip() or "Evaluated against retrieved lecture evidence."
        normalized.append({
            "claim_id": str(item["claim_id"]),
            "status": status,
            "explanation": explanation,
        })

    if not normalized:
        return fallback_batch_eval(batch)
    return normalized


def evaluate_student_evidence_to_file(
    evidence_path: Union[str, Path],
    output_path: Union[str, Path],
    course_id: str,
    lecture_id: str,
    strict_llm: bool = False,
) -> Dict[str, Any]:
    """
    Evaluates a student's claims against retrieved lecture evidence from evidence_path
    and writes explicit output_path (evaluated.json).
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")

    src = Path(evidence_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Evidence file not found: {src}")

    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("course_id") != valid_course_id or data.get("lecture_id") != valid_lecture_id:
        raise ValueError(
            f"Evidence file {src} belongs to {data.get('course_id')}/{data.get('lecture_id')}, "
            f"expected {valid_course_id}/{valid_lecture_id}."
        )

    student_id = data["student_id"]
    claims = data.get("claims", [])

    prepared_claims: List[Dict[str, Any]] = []
    for claim in claims:
        ev_list = claim.get("evidence", [])
        for ev in ev_list:
            if ev.get("course_id") != valid_course_id or ev.get("lecture_id") != valid_lecture_id:
                raise ValueError(
                    f"Cross-lecture evidence chunk '{ev.get('chunk_id')}' detected during evaluation."
                )
        prepared_claims.append({
            "claim_id": claim["claim_id"],
            "claim_text": claim["claim"],
            "evidence": ev_list,
        })

    batches = [
        prepared_claims[i : i + BATCH_SIZE]
        for i in range(0, len(prepared_claims), BATCH_SIZE)
    ]

    all_evaluations: List[Dict[str, Any]] = []
    for batch in batches:
        all_evaluations.extend(evaluate_batch(batch, strict_llm=strict_llm))

    evaluation_map = {item["claim_id"]: item for item in all_evaluations}
    fallback_map = {item["claim_id"]: item for item in fallback_batch_eval(prepared_claims)}

    final_claims: List[Dict[str, Any]] = []
    for claim in claims:
        cid = claim["claim_id"]
        eval_item = evaluation_map.get(cid) or fallback_map.get(
            cid,
            {
                "claim_id": cid,
                "status": "NOT_SUPPORTED",
                "explanation": "No supporting evidence evaluation available.",
            },
        )
        final_claims.append({
            "claim_id": cid,
            "claim": claim["claim"],
            "status": eval_item["status"],
            "explanation": eval_item["explanation"],
            "evidence": claim.get("evidence", [])[:TOP_K_EVIDENCE],
        })

    payload = {
        "student_id": student_id,
        "sanitized_student_id": data.get("sanitized_student_id", student_id),
        "course_id": valid_course_id,
        "lecture_id": valid_lecture_id,
        "total_claims": len(final_claims),
        "claims": final_claims,
    }

    dest = Path(output_path).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return payload


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate student claims strictly against retrieved lecture evidence."
    )
    parser.add_argument("--course-id", required=True, help="Explicit course identifier.")
    parser.add_argument("--lecture-id", required=True, help="Explicit lecture identifier.")
    parser.add_argument("--evidence-file", required=True, help="Explicit path to student evidence.json.")
    parser.add_argument("--output-file", required=True, help="Explicit path to output evaluated.json.")
    parser.add_argument("--strict-llm", action="store_true", help="Fail immediately on LLM API errors.")

    args = parser.parse_args(argv)
    try:
        evaluate_student_evidence_to_file(
            evidence_path=args.evidence_file,
            output_path=args.output_file,
            course_id=args.course_id,
            lecture_id=args.lecture_id,
            strict_llm=args.strict_llm,
        )
        print(f"Saved claim evaluation to {args.output_file}")
    except Exception as e:
        print(f"Error during claim evaluation: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
