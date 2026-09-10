"""CLI for building a teaching knowledge base for exactly one lecture."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from knowledge.builder import build_documents, discover_source
from knowledge.knowledge_extractor import extract_knowledge_units
from knowledge.validate_kb import validate_kb
from retrival.embedding import DEFAULT_MODEL, Embedder
from retrival.vector_store import VectorStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an evidence-preserving teaching KB for one lecture.")
    parser.add_argument("--lecture-id", required=True)
    parser.add_argument("--transcript", type=Path, help="Processed transcript JSON. Required when IDs do not match.")
    parser.add_argument("--pdf", type=Path, help="Processed PDF JSON. Required when IDs do not match.")
    args = parser.parse_args()
    processed = ROOT / "data" / "processed"
    transcript_path = args.transcript or discover_source(processed / "transcripts", args.lecture_id)
    pdf_path = args.pdf or discover_source(processed / "pdf_text", args.lecture_id)
    if transcript_path is None and pdf_path is None:
        raise SystemExit("No matching sources found. Supply --transcript and/or --pdf explicitly.")
    for path in (transcript_path, pdf_path):
        if path is not None and not path.is_file():
            raise SystemExit(f"Source file not found: {path}")

    documents, audio_count, pdf_count = build_documents(args.lecture_id, transcript_path, pdf_path)
    evidence_documents = [{**document, "document_type": "evidence"} for document in documents]
    knowledge_units = extract_knowledge_units(evidence_documents, args.lecture_id)
    print("=" * 50)
    print("BUILDING TEACHING KNOWLEDGE BASE")
    print(f"Lecture: {args.lecture_id}\nAudio knowledge chunks: {audio_count}\nPDF knowledge chunks: {pdf_count}")
    print(f"Total evidence chunks: {len(evidence_documents)}\nKnowledge units: {len(knowledge_units)}\nEmbedding model: {DEFAULT_MODEL}")
    embedder = Embedder(DEFAULT_MODEL)
    vectors = embedder.encode(document["knowledge_text"] for document in evidence_documents)
    knowledge_vectors = embedder.encode(f"{unit['concept']}. {unit['teaching_statement']}" for unit in knowledge_units)

    kb_dir = processed / "knowledge_base" / args.lecture_id
    store_dir = processed / "vector_store" / args.lecture_id
    kb_dir.mkdir(parents=True, exist_ok=True)
    # kb.json remains the backward-compatible evidence layer.
    (kb_dir / "kb.json").write_text(json.dumps(evidence_documents, indent=2, ensure_ascii=False), encoding="utf-8")
    (kb_dir / "evidence.json").write_text(json.dumps(evidence_documents, indent=2, ensure_ascii=False), encoding="utf-8")
    (kb_dir / "metadata.json").write_text(json.dumps(evidence_documents, indent=2, ensure_ascii=False), encoding="utf-8")
    (kb_dir / "knowledge_units.json").write_text(json.dumps(knowledge_units, indent=2, ensure_ascii=False), encoding="utf-8")
    import numpy as np
    np.save(kb_dir / "embeddings.npy", vectors)
    np.save(kb_dir / "knowledge_embeddings.npy", knowledge_vectors)
    VectorStore(vectors, evidence_documents).save(store_dir)
    VectorStore(knowledge_vectors, knowledge_units).save(store_dir / "knowledge")
    report = validate_kb(args.lecture_id, transcript_path, pdf_path, kb_dir, store_dir)
    (kb_dir / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    manifest = {
        "lecture_id": args.lecture_id,
        "transcript_file": transcript_path.name if transcript_path else None,
        "pdf_file": pdf_path.name if pdf_path else None,
        "audio_source_segments": report["audio_coverage"].get("transcript_segments"),
        "audio_evidence_chunks": audio_count,
        "pdf_source_pages": report["pdf_coverage"].get("source_pages"),
        "pdf_evidence_chunks": pdf_count,
        "knowledge_units": len(knowledge_units),
        "embedding_model": DEFAULT_MODEL,
        "embedding_count": int(len(vectors)),
        "embedding_dimension": int(vectors.shape[1]),
        "build_version": "1",
        "validation_status": report["overall_status"],
    }
    (kb_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if report["overall_status"] == "FAIL":
        raise SystemExit("KB build completed but validation failed; see validation_report.json.")
    print("Vector index saved.\nMetadata saved.\nKB BUILD COMPLETE\n" + "=" * 50)


if __name__ == "__main__":
    main()
