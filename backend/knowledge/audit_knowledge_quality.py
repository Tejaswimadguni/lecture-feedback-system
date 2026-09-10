"""Read-only quality audit for generated, source-grounded knowledge units."""

import argparse
import json
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def audit(lecture_id: str, kb_dir: Path) -> Dict[str, Any]:
    evidence_path = kb_dir / "evidence.json"
    if not evidence_path.is_file():
        evidence_path = kb_dir / "kb.json"
    evidence = load_json(evidence_path) if evidence_path.is_file() else []
    units_path = kb_dir / "knowledge_units.json"
    if not units_path.is_file():
        return {
            "lecture_id": lecture_id,
            "evidence_count": len(evidence),
            "knowledge_unit_count": 0,
            "grounding": {"auditable": False, "reason": "knowledge_units.json is missing"},
            "meaningfulness": {"auditable": False, "reason": "No generated knowledge units exist to evaluate."},
            "copying_analysis": {"auditable": False, "reason": "No generated knowledge units exist to compare."},
            "redundancy": {"auditable": False, "reason": "No generated knowledge units exist to compare."},
            "coverage": {"represented_evidence_chunks": 0, "unrepresented_evidence_chunks": len(evidence), "coverage_ratio": 0.0},
            "audio_analysis": {"knowledge_units": 0},
            "pdf_analysis": {"knowledge_units": 0},
            "sampled_examples": [],
            "quality_score": 0,
            "verdict": "NOT_USABLE",
            "major_failure_modes": ["The generated KB has an evidence layer but no knowledge layer artifact.", "No knowledge-unit-to-evidence traceability, semantic quality, redundancy, or knowledge retrieval audit can be performed."],
            "recommendations": ["Run the knowledge-base build that generates knowledge_units.json, then rerun this audit.", "Do not treat the existing evidence-only kb.json as a validated knowledge extraction output."],
        }

    units = load_json(units_path)
    evidence_by_id = {item.get("chunk_id"): item for item in evidence}
    duplicate_ids = [item for item, count in Counter(unit.get("knowledge_id") for unit in units).items() if count > 1]
    duplicate_concepts = [item for item, count in Counter(str(unit.get("concept", "")).strip().lower() for unit in units).items() if count > 1]
    empty_concepts = [unit.get("knowledge_id") for unit in units if not str(unit.get("concept", "")).strip()]
    empty_statements = [unit.get("knowledge_id") for unit in units if not str(unit.get("teaching_statement", "")).strip()]
    zero_refs, unsupported, direct, referenced = [], [], 0, set()
    exact_copy = near_copy = 0
    for unit in units:
        references = unit.get("evidence_chunk_ids", [])
        if not references:
            zero_refs.append(unit.get("knowledge_id"))
            continue
        linked = [evidence_by_id.get(reference) for reference in references]
        referenced.update(references)
        statement = str(unit.get("teaching_statement", "")).strip()
        source_text = " ".join(str(item.get("original_text", "")) for item in linked if item)
        if not all(linked) or unit.get("lecture_id") != lecture_id or not statement or statement not in source_text:
            unsupported.append(unit.get("knowledge_id"))
        else:
            direct += 1
            ratio = SequenceMatcher(None, statement, source_text).ratio()
            exact_copy += statement == source_text
            near_copy += ratio >= 0.85 and statement != source_text
    source_types = Counter(unit.get("source_type") for unit in units)
    sample_indexes = sorted(set(round(index * (len(units) - 1) / 7) for index in range(min(8, len(units)))))
    samples = []
    for index in sample_indexes:
        unit = units[index]
        samples.append({"knowledge_id": unit.get("knowledge_id"), "concept": unit.get("concept"), "teaching_statement": unit.get("teaching_statement"), "evidence_chunk_ids": unit.get("evidence_chunk_ids"), "quality": "DIRECTLY_GROUNDED" if unit.get("knowledge_id") not in unsupported else "UNSUPPORTED", "reason": "Automatic source-string traceability check."})
    unit_count = len(units)
    grounding_ratio = direct / unit_count if unit_count else 0.0
    score = round(100 * grounding_ratio) if not (zero_refs or unsupported) else round(70 * grounding_ratio)
    return {"lecture_id": lecture_id, "evidence_count": len(evidence), "knowledge_unit_count": unit_count,
            "grounding": {"directly_grounded": direct, "weakly_grounded": 0, "unsupported": unsupported, "zero_evidence_references": zero_refs, "automatic_source_traceability": not unsupported and not zero_refs},
            "meaningfulness": {"automatic_limit": "Pedagogical meaningfulness requires human review; samples are provided.", "empty_concepts": empty_concepts, "empty_teaching_statements": empty_statements},
            "copying_analysis": {"exact_copy_count": exact_copy, "near_copy_count": near_copy, "extractive_statement_count": unit_count},
            "redundancy": {"duplicate_knowledge_ids": duplicate_ids, "duplicate_concepts": duplicate_concepts, "near_duplicate_concepts": "not automatically classified without a semantic model"},
            "coverage": {"represented_evidence_chunks": len(referenced & set(evidence_by_id)), "unrepresented_evidence_chunks": len(evidence_by_id) - len(referenced & set(evidence_by_id)), "coverage_ratio": len(referenced & set(evidence_by_id)) / len(evidence_by_id) if evidence_by_id else 0.0},
            "audio_analysis": {"knowledge_units": source_types["audio"]}, "pdf_analysis": {"knowledge_units": source_types["pdf"]}, "sampled_examples": samples,
            "quality_score": score, "verdict": "READY_WITH_MINOR_ISSUES" if score >= 80 else "NEEDS_IMPROVEMENT",
            "major_failure_modes": ["Automatic checks cannot establish pedagogical usefulness or prove absence of hallucination."], "recommendations": ["Perform human review of the deterministic sample before student-claim verification."]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a generated knowledge layer without changing it.")
    parser.add_argument("--lecture-id", required=True)
    parser.add_argument("--kb-dir", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    kb_dir = args.kb_dir or root / "data" / "processed" / "knowledge_base" / args.lecture_id
    report = audit(args.lecture_id, kb_dir)
    output = kb_dir / "knowledge_quality_audit.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Knowledge units: {report['knowledge_unit_count']} | Score: {report['quality_score']} | Verdict: {report['verdict']}")


if __name__ == "__main__":
    main()
