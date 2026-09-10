"""Source-to-KB integrity validation. Raw source > knowledge text > embedding."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))
from knowledge.builder import load_json
from knowledge.chunker import normalize_text


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _gaps(items: List[Dict[str, Any]]) -> List[float]:
    return [float(next_item["start"]) - float(item["end"]) for item, next_item in zip(items, items[1:]) if float(next_item["start"]) > float(item["end"])]


def validate_kb(lecture_id: str, transcript_path: Optional[Path], pdf_path: Optional[Path], kb_dir: Path, store_dir: Path) -> Dict[str, Any]:
    """Validate source reconstruction, metadata, embedding order, and vector artifacts."""
    errors: List[str] = []
    warnings: List[str] = []
    documents = _read(kb_dir / "kb.json")
    metadata_path = kb_dir / "metadata.json"
    metadata = _read(metadata_path) if metadata_path.is_file() else None
    if not isinstance(documents, list):
        raise ValueError("kb.json must be a list.")
    audio = [item for item in documents if item.get("source_type") == "audio"]
    pdf = [item for item in documents if item.get("source_type") == "pdf"]
    if any(item.get("lecture_id") != lecture_id for item in documents):
        errors.append("Lecture isolation failed: KB contains a different lecture_id.")
    empty = [item.get("chunk_id") for item in documents if not str(item.get("original_text", "")).strip() or not str(item.get("knowledge_text", "")).strip()]
    if empty:
        errors.append(f"Found {len(empty)} empty chunks.")
    duplicate_groups = sum(count > 1 for count in Counter((item.get("source_type"), item.get("original_text")) for item in documents).values())
    if duplicate_groups:
        warnings.append(f"Found {duplicate_groups} exact duplicate groups; retained because source evidence may repeat.")
    altered = [item.get("chunk_id") for item in documents if normalize_text(str(item.get("original_text", ""))) != item.get("knowledge_text")]
    if altered:
        errors.append("Knowledge text is not the approved deterministic normalization of original text.")

    knowledge_path = kb_dir / "knowledge_units.json"
    knowledge_report: Dict[str, Any] = {"knowledge_units": 0, "automatic_source_traceability": False}
    if not knowledge_path.is_file():
        errors.append("Knowledge layer is missing: knowledge_units.json was not built.")
    else:
        units = _read(knowledge_path)
        evidence_by_id = {item["chunk_id"]: item for item in documents}
        invalid_units = []
        for unit in units:
            references = unit.get("evidence_chunk_ids", [])
            referenced = [evidence_by_id.get(chunk_id) for chunk_id in references]
            statement = normalize_text(str(unit.get("teaching_statement", "")))
            supported = bool(referenced) and all(item is not None for item in referenced) and any(statement in normalize_text(item["original_text"]) for item in referenced if item)
            if unit.get("lecture_id") != lecture_id or not unit.get("concept") or not statement or not supported:
                invalid_units.append(unit.get("knowledge_id"))
        if invalid_units:
            errors.append(f"Knowledge traceability validation failed for {len(invalid_units)} units.")
        knowledge_report = {"knowledge_units": len(units), "invalid_units": invalid_units,
                            "automatic_source_traceability": not invalid_units}

    audio_report: Dict[str, Any] = {"source_found": bool(transcript_path), "kb_chunks": len(audio)}
    if transcript_path:
        segments = [item for item in load_json(transcript_path).get("segments", []) if str(item.get("text", "")).strip()]
        source_text = " ".join(str(item["text"]).strip() for item in segments)
        kb_text = " ".join(str(item["original_text"]).strip() for item in audio)
        invalid = [item.get("chunk_id") for item in audio if item.get("page") is not None or item.get("start") is None or item.get("end") is None or float(item["start"]) >= float(item["end"])]
        monotonic = all(float(left["start"]) <= float(right["start"]) for left, right in zip(audio, audio[1:]))
        reconstructed = source_text == kb_text
        if not reconstructed or invalid or not monotonic or any(item.get("source_file") != transcript_path.name for item in audio):
            errors.append("Audio coverage, timestamp, or source-file validation failed.")
        kb_gaps = _gaps(audio)
        overlaps = sum(float(right["start"]) < float(left["end"]) for left, right in zip(audio, audio[1:]))
        audio_report.update({"transcript_segments": len(segments), "source_start": segments[0].get("start") if segments else None, "source_end": segments[-1].get("end") if segments else None, "kb_start": audio[0].get("start") if audio else None, "kb_end": audio[-1].get("end") if audio else None, "coverage_ratio": 1.0 if reconstructed else 0.0, "source_content_reconstructed": reconstructed, "gap_count": len(kb_gaps), "largest_gap": max(kb_gaps, default=0.0), "overlaps": overlaps, "invalid_chunks": invalid, "monotonic": monotonic})

    pdf_report: Dict[str, Any] = {"source_found": bool(pdf_path), "kb_chunks": len(pdf)}
    if pdf_path:
        pages = [item for item in load_json(pdf_path).get("pages", []) if str(item.get("text", "")).strip()]
        expected_pages, actual_pages = [item.get("page") for item in pages], [item.get("page") for item in pdf]
        reconstructed = " ".join(str(item["text"]).strip() for item in pages) == " ".join(str(item["original_text"]).strip() for item in pdf)
        invalid = [item.get("chunk_id") for item in pdf if item.get("page") is None or item.get("start") is not None or item.get("end") is not None]
        missing = sorted(set(expected_pages) - set(actual_pages))
        if not reconstructed or invalid or missing or any(item.get("source_file") != pdf_path.name for item in pdf):
            errors.append("PDF coverage, page, or source-file validation failed.")
        pdf_report.update({"source_pages": len(pages), "missing_pages": missing, "source_content_reconstructed": reconstructed, "invalid_chunks": invalid})

    embedding_report: Dict[str, Any] = {"kb_documents": len(documents), "metadata_aligned": metadata == documents}
    vectors_path, store_vectors_path, store_metadata_path = kb_dir / "embeddings.npy", store_dir / "vectors.npy", store_dir / "metadata.json"
    if not (vectors_path.is_file() and store_vectors_path.is_file() and store_metadata_path.is_file()):
        errors.append("Embeddings or vector-store artifacts are missing.")
    else:
        vectors, store_vectors, store_metadata = np.load(vectors_path), np.load(store_vectors_path), _read(store_metadata_path)
        ids = [item.get("chunk_id") for item in documents]
        aligned = len(vectors) == len(documents) and np.array_equal(vectors, store_vectors) and ids == [item.get("chunk_id") for item in store_metadata] and metadata == documents
        embedding_report.update({"embedding_count": int(len(vectors)), "embedding_dimension": int(vectors.shape[1]) if vectors.ndim == 2 else None, "nan_vectors": bool(np.isnan(vectors).any()), "infinite_vectors": bool(np.isinf(vectors).any()), "store_count": int(len(store_vectors)), "alignment": aligned})
        if not aligned or np.isnan(vectors).any() or np.isinf(vectors).any():
            errors.append("Embedding/vector-store alignment or numeric validation failed.")
    knowledge_vectors_path = kb_dir / "knowledge_embeddings.npy"
    knowledge_store = store_dir / "knowledge"
    if knowledge_path.is_file() and knowledge_vectors_path.is_file() and (knowledge_store / "vectors.npy").is_file() and (knowledge_store / "metadata.json").is_file():
        units, knowledge_vectors = _read(knowledge_path), np.load(knowledge_vectors_path)
        store_units, store_vectors = _read(knowledge_store / "metadata.json"), np.load(knowledge_store / "vectors.npy")
        knowledge_aligned = len(units) == len(knowledge_vectors) and np.array_equal(knowledge_vectors, store_vectors) and [unit["knowledge_id"] for unit in units] == [unit["knowledge_id"] for unit in store_units]
        embedding_report["knowledge"] = {"embedding_count": int(len(knowledge_vectors)), "embedding_dimension": int(knowledge_vectors.shape[1]) if knowledge_vectors.ndim == 2 else None, "alignment": knowledge_aligned, "nan_vectors": bool(np.isnan(knowledge_vectors).any()), "infinite_vectors": bool(np.isinf(knowledge_vectors).any())}
        if not knowledge_aligned or np.isnan(knowledge_vectors).any() or np.isinf(knowledge_vectors).any():
            errors.append("Knowledge embedding/vector-store alignment failed.")
    elif knowledge_path.is_file():
        errors.append("Knowledge embedding or knowledge vector-store artifacts are missing.")
    status = "FAIL" if errors else ("PASS_WITH_WARNINGS" if warnings else "PASS")
    return {"lecture_id": lecture_id, "source_authority": "RAW SOURCE > KNOWLEDGE TEXT > EMBEDDING", "audio_coverage": audio_report, "pdf_coverage": pdf_report, "content_validation": {"empty_chunks": empty, "duplicate_groups": duplicate_groups, "knowledge_text_mismatches": altered}, "knowledge_validation": knowledge_report, "embedding_validation": embedding_report, "retrieval_validation": "not_run", "errors": errors, "warnings": warnings, "overall_status": status}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a teaching KB against its selected source files.")
    parser.add_argument("--lecture-id", required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    args = parser.parse_args()
    kb_dir, store_dir = ROOT / "data" / "processed" / "knowledge_base" / args.lecture_id, ROOT / "data" / "processed" / "vector_store" / args.lecture_id
    report = validate_kb(args.lecture_id, args.transcript, args.pdf, kb_dir, store_dir)
    (kb_dir / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if report["overall_status"] == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
