import os
import json
from typing import Dict, Any, List, Optional


REQUIRED_FIELDS = [
    "chunk_id",
    "course_id",
    "course_name",
    "lecture_id",
    "lecture_title",
    "source_type",
    "source_file",
    "text",
    "start_time",
    "end_time",
    "page",
]


def create_chunk_metadata(
    chunk_id: str,
    course_id: str,
    lecture_id: str,
    source_type: str,
    text: str,
    course_name: str = "Introduction to CS",
    lecture_title: str = "Introduction",
    source_file: str = "",
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    page: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Creates a unified chunk dictionary adhering to the system's metadata schema.

    Args:
        chunk_id: Unique identifier for the chunk (e.g. MIT_6_100L_lec01_T001).
        course_id: Identifier for the course (e.g. MIT_6_100L).
        lecture_id: Identifier for the lecture (e.g. lec01).
        source_type: Type of source material ('transcript' or 'pdf').
        text: Cleaned text content of the chunk.
        course_name: Full human-readable name of the course.
        lecture_title: Title of the lecture.
        source_file: Filename of origin (e.g. lecture_01.mp4 or lecture_01.pdf).
        start_time: Start timestamp in seconds (for transcript chunks).
        end_time: End timestamp in seconds (for transcript chunks).
        page: Page number 1-indexed (for PDF chunks).

    Returns:
        Dict adhering to the unified chunk metadata specification.
    """
    if source_type not in ("transcript", "pdf"):
        raise ValueError(f"Invalid source_type '{source_type}'. Expected 'transcript' or 'pdf'.")

    chunk = {
        "chunk_id": chunk_id,
        "course_id": course_id,
        "course_name": course_name,
        "lecture_id": lecture_id,
        "lecture_title": lecture_title,
        "source_type": source_type,
        "source_file": source_file,
        "text": text,
        "start_time": float(start_time) if start_time is not None else None,
        "end_time": float(end_time) if end_time is not None else None,
        "page": int(page) if page is not None else None,
    }

    validate_chunk(chunk)
    return chunk


def validate_chunk(chunk: Dict[str, Any]) -> bool:
    """
    Validates that a chunk dict contains all required metadata fields and respects type constraints.

    Returns True if valid; raises ValueError if invalid.
    """
    for field in REQUIRED_FIELDS:
        if field not in chunk:
            raise ValueError(f"Missing required metadata field: '{field}' in chunk {chunk.get('chunk_id')}")

    source_type = chunk.get("source_type")
    if source_type == "transcript":
        if chunk.get("start_time") is None:
            raise ValueError(f"Transcript chunk '{chunk.get('chunk_id')}' must have a non-null start_time.")
        if chunk.get("end_time") is None:
            raise ValueError(f"Transcript chunk '{chunk.get('chunk_id')}' must have a non-null end_time.")
    elif source_type == "pdf":
        if chunk.get("page") is None:
            raise ValueError(f"PDF chunk '{chunk.get('chunk_id')}' must have a non-null page number.")
    else:
        raise ValueError(f"Unknown source_type '{source_type}' in chunk '{chunk.get('chunk_id')}'.")

    if not isinstance(chunk.get("text"), str) or not chunk.get("text").strip():
        raise ValueError(f"Chunk '{chunk.get('chunk_id')}' contains empty or non-string text.")

    return True


def build_dataset_metadata(all_chunks: List[Dict[str, Any]], output_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Generates summary dataset metadata for all processed chunks.

    Args:
        all_chunks: List of chunk metadata dictionaries.
        output_path: Optional file path to save the dataset metadata JSON.

    Returns:
        Dataset metadata summary dict.
    """
    transcript_chunks = [c for c in all_chunks if c.get("source_type") == "transcript"]
    pdf_chunks = [c for c in all_chunks if c.get("source_type") == "pdf"]

    course_ids = sorted(list(set(c["course_id"] for c in all_chunks if "course_id" in c)))
    lecture_ids = sorted(list(set(c["lecture_id"] for c in all_chunks if "lecture_id" in c)))

    dataset_summary = {
        "total_chunks": len(all_chunks),
        "total_transcript_chunks": len(transcript_chunks),
        "total_pdf_chunks": len(pdf_chunks),
        "courses": course_ids,
        "lectures": lecture_ids,
        "chunk_ids": [c["chunk_id"] for c in all_chunks],
    }

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(dataset_summary, f, indent=2, ensure_ascii=False)

    return dataset_summary
