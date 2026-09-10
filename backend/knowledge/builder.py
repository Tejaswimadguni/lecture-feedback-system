"""Build an evidence-preserving teaching knowledge base from processed JSON."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .chunker import audio_knowledge_chunks, pdf_knowledge_chunks


def load_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        data = json.load(source)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return data


def discover_source(directory: Path, lecture_id: str) -> Optional[Path]:
    matches = sorted(path for path in directory.glob("*.json") if lecture_id.lower() in path.stem.lower())
    if len(matches) > 1:
        raise ValueError(f"More than one source matches lecture ID '{lecture_id}' in {directory}; provide an explicit path.")
    return matches[0] if matches else None


def build_documents(lecture_id: str, transcript_path: Optional[Path], pdf_path: Optional[Path]) -> Tuple[List[Dict[str, Any]], int, int]:
    """Create common KB documents while retaining every source reference."""
    if transcript_path is None and pdf_path is None:
        raise ValueError("Provide at least one transcript or PDF source.")
    documents: List[Dict[str, Any]] = []
    audio_count = pdf_count = 0

    if transcript_path:
        transcript = load_json(transcript_path)
        segments = transcript.get("segments")
        if not isinstance(segments, list):
            raise ValueError(f"Transcript file {transcript_path} has no 'segments' list.")
        for sequence, chunk in enumerate(audio_knowledge_chunks(segments), start=1):
            documents.append({
                "chunk_id": f"{lecture_id}_audio_{sequence:04d}", "lecture_id": lecture_id,
                "source_type": "audio", "source_file": transcript_path.name,
                "original_text": chunk["original_text"], "knowledge_text": chunk["knowledge_text"],
                "topic": None, "start": chunk["start"], "end": chunk["end"], "page": None,
                "sequence": sequence,
            })
        audio_count = len(documents)

    if pdf_path:
        pdf = load_json(pdf_path)
        pages = pdf.get("pages")
        if not isinstance(pages, list):
            raise ValueError(f"PDF file {pdf_path} has no 'pages' list.")
        pdf_chunks = pdf_knowledge_chunks(pages)
        for sequence, chunk in enumerate(pdf_chunks, start=1):
            documents.append({
                "chunk_id": f"{lecture_id}_pdf_page_{chunk['page']}_chunk_{sequence:04d}", "lecture_id": lecture_id,
                "source_type": "pdf", "source_file": pdf_path.name,
                "original_text": chunk["original_text"], "knowledge_text": chunk["knowledge_text"],
                "topic": None, "start": None, "end": None, "page": chunk["page"], "sequence": sequence,
            })
        pdf_count = len(pdf_chunks)
    return documents, audio_count, pdf_count
