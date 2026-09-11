import os
import json
import logging
from typing import Dict, Any, List

try:
    from .transcript_cleaner import clean_transcript
    from .transcript_chunker import chunk_transcript
    from .pdf_cleaner import clean_pdf_pages
    from .pdf_chunker import chunk_pdf
    from .metadata import build_dataset_metadata
except ImportError:
    from transcript_cleaner import clean_transcript
    from transcript_chunker import chunk_transcript
    from pdf_cleaner import clean_pdf_pages
    from pdf_chunker import chunk_pdf
    from metadata import build_dataset_metadata

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def process_transcript_file(
    raw_transcript_path: str,
    transcripts_dir: str,
    course_id: str = "MIT_6_100L",
    lecture_id: str = "lec01",
    course_name: str = "Introduction to CS",
    lecture_title: str = "Introduction",
    source_file: str = "lecture_01.mp4",
) -> List[Dict[str, Any]]:
    """
    Processes a raw transcript JSON file through cleaning, chunking, and metadata assignment.
    Saves lecture_01_raw.json, lecture_01_clean.json, and lecture_01_chunks.json in transcripts_dir.
    """
    with open(raw_transcript_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    segments = raw_data.get("segments", [])

    # 1. Preserve raw data file as lecture_01_raw.json
    raw_out_path = os.path.join(transcripts_dir, "lecture_01_raw.json")
    if not os.path.exists(raw_out_path) or os.path.abspath(raw_transcript_path) != os.path.abspath(raw_out_path):
        with open(raw_out_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved preserved raw transcript to {raw_out_path}")

    # 2. Clean transcript
    cleaned_segments = clean_transcript(segments)
    clean_out_path = os.path.join(transcripts_dir, "lecture_01_clean.json")
    clean_data = {
        "lecture_id": lecture_id,
        "segments": cleaned_segments
    }
    with open(clean_out_path, "w", encoding="utf-8") as f:
        json.dump(clean_data, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved clean transcript to {clean_out_path}")

    # 3. Chunk transcript
    chunks = chunk_transcript(
        segments=cleaned_segments,
        course_id=course_id,
        lecture_id=lecture_id,
        target_word_count=350,
        overlap_word_count=50,
        course_name=course_name,
        lecture_title=lecture_title,
        source_file=source_file,
    )
    chunks_out_path = os.path.join(transcripts_dir, "lecture_01_chunks.json")
    with open(chunks_out_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved transcript chunks to {chunks_out_path} ({len(chunks)} chunks)")

    return chunks


def process_pdf_file(
    raw_pdf_path: str,
    pdf_text_dir: str,
    course_id: str = "MIT_6_100L",
    lecture_id: str = "lec01",
    course_name: str = "Introduction to CS",
    lecture_title: str = "Introduction",
    source_file: str = "lecture_01.pdf",
) -> List[Dict[str, Any]]:
    """
    Processes a raw PDF extracted JSON file through cleaning, page-aware chunking, and metadata assignment.
    Saves lecture_01_raw.json, lecture_01_clean.json, and lecture_01_chunks.json in pdf_text_dir.
    """
    with open(raw_pdf_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    pages = raw_data.get("pages", [])

    # 1. Preserve raw data file as lecture_01_raw.json
    raw_out_path = os.path.join(pdf_text_dir, "lecture_01_raw.json")
    if not os.path.exists(raw_out_path) or os.path.abspath(raw_pdf_path) != os.path.abspath(raw_out_path):
        with open(raw_out_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved preserved raw PDF text to {raw_out_path}")

    # 2. Clean PDF pages
    cleaned_pages = clean_pdf_pages(pages)
    clean_out_path = os.path.join(pdf_text_dir, "lecture_01_clean.json")
    clean_data = {
        "lecture_id": lecture_id,
        "pages": cleaned_pages
    }
    with open(clean_out_path, "w", encoding="utf-8") as f:
        json.dump(clean_data, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved clean PDF text to {clean_out_path}")

    # 3. Chunk PDF
    chunks = chunk_pdf(
        pages=cleaned_pages,
        course_id=course_id,
        lecture_id=lecture_id,
        target_word_count=350,
        course_name=course_name,
        lecture_title=lecture_title,
        source_file=source_file,
    )
    chunks_out_path = os.path.join(pdf_text_dir, "lecture_01_chunks.json")
    with open(chunks_out_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved PDF chunks to {chunks_out_path} ({len(chunks)} chunks)")

    return chunks


def run_section2_pipeline() -> Dict[str, Any]:
    """
    Executes Section 2 full data pipeline on available processed data.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    transcripts_dir = os.path.join(base_dir, "data", "processed", "transcripts")
    pdf_text_dir = os.path.join(base_dir, "data", "processed", "pdf_text")
    metadata_dir = os.path.join(base_dir, "data", "processed", "metadata")

    os.makedirs(transcripts_dir, exist_ok=True)
    os.makedirs(pdf_text_dir, exist_ok=True)
    os.makedirs(metadata_dir, exist_ok=True)

    all_chunks = []

    # Process Transcript if available
    raw_transcript_candidate = os.path.join(transcripts_dir, "lecture_01_transcript.json")
    if not os.path.exists(raw_transcript_candidate):
        raw_transcript_candidate = os.path.join(transcripts_dir, "lecture_01_raw.json")

    if os.path.exists(raw_transcript_candidate):
        logger.info(f"Processing transcript file: {raw_transcript_candidate}")
        t_chunks = process_transcript_file(
            raw_transcript_path=raw_transcript_candidate,
            transcripts_dir=transcripts_dir,
            course_id="MIT_6_100L",
            lecture_id="lec01",
        )
        all_chunks.extend(t_chunks)

    # Process PDF if available
    raw_pdf_candidate = os.path.join(pdf_text_dir, "lecture_01_notes.json")
    if not os.path.exists(raw_pdf_candidate):
        raw_pdf_candidate = os.path.join(pdf_text_dir, "lecture_01_raw.json")

    if os.path.exists(raw_pdf_candidate):
        logger.info(f"Processing PDF file: {raw_pdf_candidate}")
        p_chunks = process_pdf_file(
            raw_pdf_path=raw_pdf_candidate,
            pdf_text_dir=pdf_text_dir,
            course_id="MIT_6_100L",
            lecture_id="lec01",
        )
        all_chunks.extend(p_chunks)

    # Build dataset metadata summary
    meta_path = os.path.join(metadata_dir, "dataset_metadata.json")
    summary = build_dataset_metadata(all_chunks, output_path=meta_path)
    logger.info(f"Saved dataset metadata summary to {meta_path}")

    return summary


if __name__ == "__main__":
    run_section2_pipeline()
