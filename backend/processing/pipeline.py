import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.paths import (
    get_lecture_paths,
    validate_identifier,
    validate_non_empty_text,
)
from backend.processing.metadata import build_dataset_metadata, validate_chunk
from backend.processing.pdf_chunker import chunk_pdf
from backend.processing.pdf_cleaner import clean_pdf_pages
from backend.processing.transcript_chunker import chunk_transcript
from backend.processing.transcript_cleaner import clean_transcript

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def process_transcript_file(
    raw_transcript_path: str,
    processed_dir: str,
    course_id: str,
    lecture_id: str,
    course_name: str,
    lecture_title: str,
    source_file: str,
) -> List[Dict[str, Any]]:
    """
    Processes a lecture's raw transcript JSON through cleaning, chunking, and metadata assignment.
    Saves transcript_raw.json, transcript_clean.json, and transcript_chunks.json inside processed_dir.
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")
    valid_course_name = validate_non_empty_text(course_name, "course_name")
    valid_lecture_title = validate_non_empty_text(lecture_title, "lecture_title")

    if not os.path.exists(raw_transcript_path):
        raise FileNotFoundError(f"Raw transcript file not found: {raw_transcript_path}")

    os.makedirs(processed_dir, exist_ok=True)

    with open(raw_transcript_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    segments = raw_data.get("segments", [])

    raw_out_path = os.path.join(processed_dir, "transcript_raw.json")
    if os.path.abspath(raw_transcript_path) != os.path.abspath(raw_out_path):
        with open(raw_out_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved raw transcript to {raw_out_path}")

    cleaned_segments = clean_transcript(segments)
    clean_out_path = os.path.join(processed_dir, "transcript_clean.json")
    clean_data = {
        "course_id": valid_course_id,
        "lecture_id": valid_lecture_id,
        "segments": cleaned_segments,
    }
    with open(clean_out_path, "w", encoding="utf-8") as f:
        json.dump(clean_data, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved clean transcript to {clean_out_path}")

    chunks = chunk_transcript(
        segments=cleaned_segments,
        course_id=valid_course_id,
        lecture_id=valid_lecture_id,
        target_word_count=350,
        overlap_word_count=50,
        course_name=valid_course_name,
        lecture_title=valid_lecture_title,
        source_file=source_file,
    )
    for chunk in chunks:
        validate_chunk(chunk)

    chunks_out_path = os.path.join(processed_dir, "transcript_chunks.json")
    with open(chunks_out_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved transcript chunks to {chunks_out_path} ({len(chunks)} chunks)")

    return chunks


def process_pdf_file(
    raw_pdf_path: str,
    processed_dir: str,
    course_id: str,
    lecture_id: str,
    course_name: str,
    lecture_title: str,
    source_file: str,
) -> List[Dict[str, Any]]:
    """
    Processes a lecture's raw PDF extracted JSON through cleaning, page-aware chunking, and metadata assignment.
    Saves pdf_raw.json, pdf_clean.json, and pdf_chunks.json inside processed_dir.
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")
    valid_course_name = validate_non_empty_text(course_name, "course_name")
    valid_lecture_title = validate_non_empty_text(lecture_title, "lecture_title")

    if not os.path.exists(raw_pdf_path):
        raise FileNotFoundError(f"Raw PDF extraction file not found: {raw_pdf_path}")

    os.makedirs(processed_dir, exist_ok=True)

    with open(raw_pdf_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    pages = raw_data.get("pages", [])

    raw_out_path = os.path.join(processed_dir, "pdf_raw.json")
    if os.path.abspath(raw_pdf_path) != os.path.abspath(raw_out_path):
        with open(raw_out_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved raw PDF text to {raw_out_path}")

    cleaned_pages = clean_pdf_pages(pages)
    clean_out_path = os.path.join(processed_dir, "pdf_clean.json")
    clean_data = {
        "course_id": valid_course_id,
        "lecture_id": valid_lecture_id,
        "pages": cleaned_pages,
    }
    with open(clean_out_path, "w", encoding="utf-8") as f:
        json.dump(clean_data, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved clean PDF text to {clean_out_path}")

    chunks = chunk_pdf(
        pages=cleaned_pages,
        course_id=valid_course_id,
        lecture_id=valid_lecture_id,
        target_word_count=350,
        course_name=valid_course_name,
        lecture_title=valid_lecture_title,
        source_file=source_file,
    )
    for chunk in chunks:
        validate_chunk(chunk)

    chunks_out_path = os.path.join(processed_dir, "pdf_chunks.json")
    with open(chunks_out_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved PDF chunks to {chunks_out_path} ({len(chunks)} chunks)")

    return chunks


def run_processing_pipeline(
    course_id: str,
    lecture_id: str,
    course_name: str,
    lecture_title: str,
    data_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes the cleaning, chunking, and metadata consolidation stage strictly for an explicitly
    specified lecture directory under backend/data/lectures/{course_id}/{lecture_id}/.
    """
    lpaths = get_lecture_paths(course_id, lecture_id, data_root=data_root)
    valid_course_name = validate_non_empty_text(course_name, "course_name")
    valid_lecture_title = validate_non_empty_text(lecture_title, "lecture_title")

    lpaths.ensure_dirs()
    all_chunks: List[Dict[str, Any]] = []

    if lpaths.transcript_raw.exists():
        with open(lpaths.transcript_raw, "r", encoding="utf-8") as f:
            t_meta = json.load(f)
        t_source = t_meta.get("source_file", "")
        t_chunks = process_transcript_file(
            raw_transcript_path=str(lpaths.transcript_raw),
            processed_dir=str(lpaths.processed_dir),
            course_id=lpaths.course_id,
            lecture_id=lpaths.lecture_id,
            course_name=valid_course_name,
            lecture_title=valid_lecture_title,
            source_file=t_source,
        )
        all_chunks.extend(t_chunks)

    if lpaths.pdf_raw.exists():
        with open(lpaths.pdf_raw, "r", encoding="utf-8") as f:
            p_meta = json.load(f)
        p_source = p_meta.get("source_file", "")
        p_chunks = process_pdf_file(
            raw_pdf_path=str(lpaths.pdf_raw),
            processed_dir=str(lpaths.processed_dir),
            course_id=lpaths.course_id,
            lecture_id=lpaths.lecture_id,
            course_name=valid_course_name,
            lecture_title=valid_lecture_title,
            source_file=p_source,
        )
        all_chunks.extend(p_chunks)

    if not all_chunks:
        raise ValueError(
            f"No raw transcript or PDF extraction files produced valid chunks for "
            f"{lpaths.course_id}/{lpaths.lecture_id} in {lpaths.processed_dir}."
        )

    summary = build_dataset_metadata(all_chunks, output_path=str(lpaths.dataset_metadata))
    logger.info(f"Saved dataset metadata summary to {lpaths.dataset_metadata}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Process extracted lecture transcript and PDF into validated chunks.")
    parser.add_argument("--course-id", required=True, help="Explicit course identifier.")
    parser.add_argument("--lecture-id", required=True, help="Explicit lecture identifier.")
    parser.add_argument("--course-name", required=True, help="Course display name.")
    parser.add_argument("--lecture-title", required=True, help="Lecture display title.")
    parser.add_argument("--data-root", default=None, help="Optional custom data root directory.")

    args = parser.parse_args()
    try:
        run_processing_pipeline(
            course_id=args.course_id,
            lecture_id=args.lecture_id,
            course_name=args.course_name,
            lecture_title=args.lecture_title,
            data_root=args.data_root,
        )
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
