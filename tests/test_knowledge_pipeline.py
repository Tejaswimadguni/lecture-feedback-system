import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from knowledge.builder import build_documents
from knowledge.chunker import normalize_text
from knowledge.knowledge_extractor import extract_knowledge_units
from retrival.vector_store import VectorStore
import numpy as np


def test_existing_sources_preserve_evidence_metadata():
    transcript_path = next((ROOT / "data" / "processed" / "transcripts").glob("*.json"))
    pdf_path = next((ROOT / "data" / "processed" / "pdf_text").glob("*.json"))
    documents, audio_count, pdf_count = build_documents("lecture01", transcript_path, pdf_path)

    assert audio_count > 0
    assert pdf_count > 0
    assert len(documents) == audio_count + pdf_count
    audio = next(document for document in documents if document["source_type"] == "audio")
    pdf = next(document for document in documents if document["source_type"] == "pdf")
    assert audio["start"] is not None and audio["end"] is not None and audio["page"] is None
    assert pdf["page"] is not None and pdf["start"] is None and pdf["end"] is None
    assert audio["original_text"] and audio["knowledge_text"]
    assert pdf["original_text"] and pdf["knowledge_text"]
    assert all(document["knowledge_text"] == normalize_text(document["original_text"]) for document in documents)
    assert [document["lecture_id"] for document in documents] == ["lecture01"] * len(documents)
    units = extract_knowledge_units(documents, "lecture01")
    evidence_ids = {document["chunk_id"] for document in documents}
    assert units
    assert all(unit["lecture_id"] == "lecture01" and unit["evidence_chunk_ids"] for unit in units)
    assert all(set(unit["evidence_chunk_ids"]).issubset(evidence_ids) for unit in units)
    assert all(unit["teaching_statement"] in normalize_text(next(document for document in documents if document["chunk_id"] == unit["evidence_chunk_ids"][0])["original_text"]) for unit in units)


def test_vector_store_returns_matching_metadata_in_vector_order(tmp_path):
    metadata = [{"chunk_id": "first"}, {"chunk_id": "second"}]
    store = VectorStore(np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32), metadata)
    store.save(tmp_path)
    results = VectorStore.load(tmp_path).search(np.array([0.0, 1.0]), top_k=1)
    assert results[0]["chunk_id"] == "second"
