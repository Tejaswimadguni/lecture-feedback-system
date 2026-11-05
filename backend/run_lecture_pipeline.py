#!/usr/bin/env python3
"""
Master Lecture Ingestion Pipeline
=================================
Executes the strict lecture-isolated end-to-end ingestion and indexing pipeline:
1. Identifier & input file validation
2. Lecture-isolated directory creation under backend/data/lectures/{course_id}/{lecture_id}/
3. Raw audio/PDF preservation in raw/
4. Audio transcription via Whisper -> processed/transcript_raw.json
5. Transcript cleaning -> processed/transcript_clean.json
6. Timestamp-preserving transcript chunking -> processed/transcript_chunks.json
7. PDF page extraction -> processed/pdf_raw.json
8. PDF cleaning -> processed/pdf_clean.json
9. Page-aware PDF chunking -> processed/pdf_chunks.json
10. Lecture-specific metadata & derived concept summary -> metadata/dataset_metadata.json
11. Independent lecture embeddings & FAISS index -> knowledge_base/{index.faiss, embeddings.npy, chunk_mapping.json}

Usage:
    python backend/run_lecture_pipeline.py \
        --course-id DBMS \
        --lecture-id DBMS_lect1 \
        --course-name "Database Management Systems" \
        --lecture-title "Normalization" \
        --audio "data/raw/audio/normalization.mp3" \
        --pdf "data/raw/pdf/normalization.pdf"
"""

import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("lecture_pipeline")

# Resolve project root and ensure correct sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.paths import (
    SUPPORTED_AUDIO_EXTENSIONS,
    SUPPORTED_PDF_EXTENSIONS,
    compute_file_sha256,
    get_lecture_paths,
    validate_audio_file,
    validate_identifier,
    validate_non_empty_text,
    validate_pdf_file,
)
from backend.processing.metadata import build_dataset_metadata, validate_chunk
from backend.processing.pdf_chunker import chunk_pdf
from backend.processing.pdf_cleaner import clean_pdf_pages
from backend.processing.transcript_chunker import chunk_transcript
from backend.processing.transcript_cleaner import clean_transcript
from backend.retrival.build_index import build_lecture_index


def print_stage_banner(stage_num: int, total_stages: int, title: str) -> None:
    """Prints a formatted console banner for pipeline stages."""
    print(f"\n{'=' * 70}")
    print(f" [Stage {stage_num}/{total_stages}] {title.upper()}")
    print(f"{'=' * 70}")


def _preserve_raw_file(src_path: Path, raw_dir: Path, allowed_extensions: set[str]) -> Path:
    """
    Copies an input source file into the lecture's isolated raw/ directory without collisions.
    Removes stale raw files of the same media category from prior runs of this same lecture
    when replaced by a newly named file, while safely skipping copy if src == dst.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest_path = (raw_dir / src_path.name).resolve()

    # Clean stale raw files of the same category from previous runs of this specific lecture
    for existing in raw_dir.iterdir():
        if (
            existing.is_file()
            and existing.suffix.lower() in allowed_extensions
            and existing.resolve() != dest_path
            and existing.resolve() != src_path.resolve()
        ):
            existing.unlink()

    if src_path.resolve() != dest_path:
        shutil.copy2(src_path, dest_path)

    return dest_path


def _can_reuse_cached_transcript(
    transcript_raw_path: Path,
    course_id: str,
    lecture_id: str,
    audio_sha256: str,
    whisper_model: str,
) -> Optional[Dict[str, Any]]:
    """
    Returns cached raw transcript dict ONLY if course_id, lecture_id, source file SHA-256,
    and whisper_model all match identically. Never falls back to any other file.
    """
    if not transcript_raw_path.exists():
        return None
    try:
        with open(transcript_raw_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if (
            isinstance(cached, dict)
            and cached.get("course_id") == course_id
            and cached.get("lecture_id") == lecture_id
            and cached.get("source_sha256") == audio_sha256
            and cached.get("whisper_model") == whisper_model
            and isinstance(cached.get("segments"), list)
        ):
            return cached
    except Exception:
        return None
    return None


def _can_reuse_cached_pdf(
    pdf_raw_path: Path,
    course_id: str,
    lecture_id: str,
    pdf_sha256: str,
) -> Optional[Dict[str, Any]]:
    """
    Returns cached raw PDF dict ONLY if course_id, lecture_id, and source file SHA-256
    all match identically.
    """
    if not pdf_raw_path.exists():
        return None
    try:
        with open(pdf_raw_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if (
            isinstance(cached, dict)
            and cached.get("course_id") == course_id
            and cached.get("lecture_id") == lecture_id
            and cached.get("source_sha256") == pdf_sha256
            and isinstance(cached.get("pages"), list)
        ):
            return cached
    except Exception:
        return None
    return None


def run_pipeline(
    course_id: str,
    lecture_id: str,
    course_name: str,
    lecture_title: str,
    audio_path: Optional[Union[str, Path]] = None,
    pdf_path: Optional[Union[str, Path]] = None,
    audio_only: bool = False,
    pdf_only: bool = False,
    whisper_model: str = "base",
    device: Optional[str] = None,
    force_reprocess: bool = False,
    data_root: Optional[Union[str, Path]] = None,
    target_word_count: int = 350,
    overlap_word_count: int = 50,
) -> Dict[str, Any]:
    """
    Executes the complete lecture-isolated ingestion, processing, and FAISS indexing pipeline.
    """
    start_time = time.time()
    total_stages = 5

    # 1. Validate mandatory identifiers and descriptive fields
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")
    valid_course_name = validate_non_empty_text(course_name, "course_name")
    valid_lecture_title = validate_non_empty_text(lecture_title, "lecture_title")

    if audio_only and pdf_only:
        raise ValueError("Cannot specify both --audio-only and --pdf-only simultaneously.")

    if audio_only:
        if not audio_path:
            raise ValueError("--audio is required when --audio-only is enabled.")
        if pdf_path:
            raise ValueError("--pdf must not be provided when --audio-only is enabled.")
    elif pdf_only:
        if not pdf_path:
            raise ValueError("--pdf is required when --pdf-only is enabled.")
        if audio_path:
            raise ValueError("--audio must not be provided when --pdf-only is enabled.")
    else:
        # Standard workflow requires both audio and PDF explicitly
        if not audio_path or not str(audio_path).strip():
            raise ValueError(
                "Both --audio and --pdf are required for standard lecture ingestion "
                "(or pass --pdf-only explicitly)."
            )
        if not pdf_path or not str(pdf_path).strip():
            raise ValueError(
                "Both --audio and --pdf are required for standard lecture ingestion "
                "(or pass --audio-only explicitly)."
            )

    valid_audio: Optional[Path] = validate_audio_file(audio_path) if audio_path else None
    valid_pdf: Optional[Path] = validate_pdf_file(pdf_path) if pdf_path else None

    # 2. Construct and create lecture-specific directories
    lpaths = get_lecture_paths(valid_course_id, valid_lecture_id, data_root=data_root)
    lpaths.ensure_dirs()

    # 3. Copy/preserve raw files in this lecture's raw/ directory
    preserved_audio: Optional[Path] = None
    preserved_pdf: Optional[Path] = None
    audio_sha256: Optional[str] = None
    pdf_sha256: Optional[str] = None

    if valid_audio is not None:
        audio_sha256 = compute_file_sha256(valid_audio)
        preserved_audio = _preserve_raw_file(valid_audio, lpaths.raw_dir, SUPPORTED_AUDIO_EXTENSIONS)

    if valid_pdf is not None:
        pdf_sha256 = compute_file_sha256(valid_pdf)
        preserved_pdf = _preserve_raw_file(valid_pdf, lpaths.raw_dir, SUPPORTED_PDF_EXTENSIONS)

    print("\n" + "#" * 70)
    print(" LECTURE FEEDBACK SYSTEM - ISOLATED LECTURE INGESTION PIPELINE")
    print("#" * 70)
    print(f" Course ID:      {valid_course_id} ({valid_course_name})")
    print(f" Lecture ID:     {valid_lecture_id} ({valid_lecture_title})")
    print(f" Audio Input:    {valid_audio if valid_audio else '[Audio-Skipped: PDF-only mode]'}")
    print(f" PDF Input:      {valid_pdf if valid_pdf else '[PDF-Skipped: Audio-only mode]'}")
    print(f" Lecture Root:   {lpaths.lecture_dir}")
    print(f" Knowledge Base: {lpaths.knowledge_base_dir}")

    transcript_chunks: List[Dict[str, Any]] = []
    pdf_chunks: List[Dict[str, Any]] = []

    # =========================================================================
    # STAGE 1 & 2: Audio Transcription, Cleaning, and Chunking
    # =========================================================================
    if preserved_audio is not None and audio_sha256 is not None:
        print_stage_banner(1, total_stages, "Audio Ingestion & Whisper Transcription")

        cached_transcript = (
            None
            if force_reprocess
            else _can_reuse_cached_transcript(
                transcript_raw_path=lpaths.transcript_raw,
                course_id=valid_course_id,
                lecture_id=valid_lecture_id,
                audio_sha256=audio_sha256,
                whisper_model=whisper_model,
            )
        )

        if cached_transcript is not None:
            logger.info(
                f"Reusing verified cached transcript for {valid_course_id}/{valid_lecture_id} "
                f"(SHA-256 & model='{whisper_model}' match)."
            )
            transcription_result = cached_transcript
        else:
            logger.info(
                f"Transcribing audio '{preserved_audio.name}' using Whisper model '{whisper_model}'..."
            )
            from backend.ingestion.audio import transcribe_audio
            transcription_result = transcribe_audio(
                audio_path=str(preserved_audio),
                lecture_id=valid_lecture_id,
                course_id=valid_course_id,
                model_size=whisper_model,
                device=device,
            )
            transcription_result["course_id"] = valid_course_id
            transcription_result["lecture_id"] = valid_lecture_id
            transcription_result["source_file"] = preserved_audio.name
            transcription_result["source_sha256"] = audio_sha256
            transcription_result["whisper_model"] = whisper_model

            with open(lpaths.transcript_raw, "w", encoding="utf-8") as f:
                json.dump(transcription_result, f, indent=2, ensure_ascii=False)

        raw_segments = transcription_result.get("segments", [])
        logger.info(f"Loaded {len(raw_segments)} raw transcript segments.")

        print_stage_banner(2, total_stages, "Transcript Cleaning & Semantic Chunking")
        cleaned_segments = clean_transcript(raw_segments)
        logger.info(f"Cleaned {len(cleaned_segments)} segments.")

        clean_data = {
            "course_id": valid_course_id,
            "lecture_id": valid_lecture_id,
            "source_file": preserved_audio.name,
            "segments": cleaned_segments,
        }
        with open(lpaths.transcript_clean, "w", encoding="utf-8") as f:
            json.dump(clean_data, f, indent=2, ensure_ascii=False)

        transcript_chunks = chunk_transcript(
            segments=cleaned_segments,
            course_id=valid_course_id,
            lecture_id=valid_lecture_id,
            target_word_count=target_word_count,
            overlap_word_count=overlap_word_count,
            course_name=valid_course_name,
            lecture_title=valid_lecture_title,
            source_file=preserved_audio.name,
        )
        with open(lpaths.transcript_chunks, "w", encoding="utf-8") as f:
            json.dump(transcript_chunks, f, indent=2, ensure_ascii=False)
        logger.info(f"Constructed {len(transcript_chunks)} transcript chunks -> {lpaths.transcript_chunks}")
    else:
        print_stage_banner(1, total_stages, "Audio Ingestion (Skipped - PDF-Only Mode)")
        print_stage_banner(2, total_stages, "Transcript Chunking (Skipped - PDF-Only Mode)")
        for stale_t in (lpaths.transcript_raw, lpaths.transcript_clean, lpaths.transcript_chunks):
            if stale_t.exists():
                stale_t.unlink()

    # =========================================================================
    # STAGE 3: PDF Extraction, Cleaning, and Chunking
    # =========================================================================
    if preserved_pdf is not None and pdf_sha256 is not None:
        print_stage_banner(3, total_stages, "PDF Extraction, Cleaning & Page-Aware Chunking")

        cached_pdf = (
            None
            if force_reprocess
            else _can_reuse_cached_pdf(
                pdf_raw_path=lpaths.pdf_raw,
                course_id=valid_course_id,
                lecture_id=valid_lecture_id,
                pdf_sha256=pdf_sha256,
            )
        )

        if cached_pdf is not None:
            logger.info(
                f"Reusing verified cached PDF extraction for {valid_course_id}/{valid_lecture_id} "
                f"(SHA-256 matches)."
            )
            pdf_raw_data = cached_pdf
        else:
            logger.info(f"Extracting text from PDF '{preserved_pdf.name}'...")
            from backend.ingestion.pdf import extract_pdf_text
            pdf_raw_data = extract_pdf_text(
                pdf_path=str(preserved_pdf),
                lecture_id=valid_lecture_id,
                course_id=valid_course_id,
            )
            pdf_raw_data["course_id"] = valid_course_id
            pdf_raw_data["lecture_id"] = valid_lecture_id
            pdf_raw_data["source_file"] = preserved_pdf.name
            pdf_raw_data["source_sha256"] = pdf_sha256

            with open(lpaths.pdf_raw, "w", encoding="utf-8") as f:
                json.dump(pdf_raw_data, f, indent=2, ensure_ascii=False)

        raw_pages = pdf_raw_data.get("pages", [])
        logger.info(f"Extracted {len(raw_pages)} PDF pages.")

        cleaned_pages = clean_pdf_pages(raw_pages)
        logger.info(f"Cleaned {len(cleaned_pages)} non-empty PDF pages.")

        pdf_clean_data = {
            "course_id": valid_course_id,
            "lecture_id": valid_lecture_id,
            "source_file": preserved_pdf.name,
            "pages": cleaned_pages,
        }
        with open(lpaths.pdf_clean, "w", encoding="utf-8") as f:
            json.dump(pdf_clean_data, f, indent=2, ensure_ascii=False)

        pdf_chunks = chunk_pdf(
            pages=cleaned_pages,
            course_id=valid_course_id,
            lecture_id=valid_lecture_id,
            target_word_count=target_word_count,
            course_name=valid_course_name,
            lecture_title=valid_lecture_title,
            source_file=preserved_pdf.name,
        )
        with open(lpaths.pdf_chunks, "w", encoding="utf-8") as f:
            json.dump(pdf_chunks, f, indent=2, ensure_ascii=False)
        logger.info(f"Constructed {len(pdf_chunks)} PDF chunks -> {lpaths.pdf_chunks}")
    else:
        print_stage_banner(3, total_stages, "PDF Extraction & Chunking (Skipped - Audio-Only Mode)")
        for stale_p in (lpaths.pdf_raw, lpaths.pdf_clean, lpaths.pdf_chunks):
            if stale_p.exists():
                stale_p.unlink()

    # =========================================================================
    # STAGE 4: Chunk Validation & Lecture-Specific Metadata Consolidation
    # =========================================================================
    print_stage_banner(4, total_stages, "Chunk Validation & Lecture Metadata")
    lecture_chunks = transcript_chunks + pdf_chunks
    if not lecture_chunks:
        raise ValueError(
            f"No valid chunks were generated for {valid_course_id}/{valid_lecture_id}. "
            "Verify that the supplied audio/PDF files contain extractable content."
        )

    for chunk in lecture_chunks:
        validate_chunk(chunk)

    extra_meta: Dict[str, Any] = {
        "course_id": valid_course_id,
        "course_name": valid_course_name,
        "lecture_id": valid_lecture_id,
        "lecture_title": valid_lecture_title,
        "source_files": {
            "audio": preserved_audio.name if preserved_audio else None,
            "audio_sha256": audio_sha256,
            "pdf": preserved_pdf.name if preserved_pdf else None,
            "pdf_sha256": pdf_sha256,
        },
        "processing_config": {
            "whisper_model": whisper_model if preserved_audio else None,
            "target_word_count": target_word_count,
            "overlap_word_count": overlap_word_count,
        },
    }

    dataset_summary = build_dataset_metadata(
        lecture_chunks,
        output_path=str(lpaths.dataset_metadata),
        extra_metadata=extra_meta,
    )
    logger.info(f"Saved lecture metadata to {lpaths.dataset_metadata}")

    # =========================================================================
    # STAGE 5: Independent Lecture Embeddings & FAISS Knowledge Base
    # =========================================================================
    print_stage_banner(5, total_stages, "Independent Lecture Embeddings & FAISS Indexing")
    kb_summary = build_lecture_index(
        course_id=valid_course_id,
        lecture_id=valid_lecture_id,
        chunks=lecture_chunks,
        data_root=lpaths.data_root,
    )

    elapsed_time = time.time() - start_time
    print("\n" + "=" * 70)
    print(" LECTURE INGESTION PIPELINE COMPLETED SUCCESSFULLY")
    print("=" * 70)
    print(f" Course:              {valid_course_id} ({valid_course_name})")
    print(f" Lecture:             {valid_lecture_id} ({valid_lecture_title})")
    print(f" Raw Audio Saved:     {preserved_audio if preserved_audio else 'N/A'}")
    print(f" Raw PDF Saved:       {preserved_pdf if preserved_pdf else 'N/A'}")
    print(f" Transcript Chunks:   {len(transcript_chunks)}")
    print(f" PDF Chunks:          {len(pdf_chunks)}")
    print(f" Total Lecture Chunks:{kb_summary['total_vectors']}")
    print(f" Metadata Path:       {lpaths.dataset_metadata}")
    print(f" FAISS Index Path:    {lpaths.faiss_index}")
    print(f" Embeddings Path:     {lpaths.embeddings}")
    print(f" Chunk Mapping Path:  {lpaths.chunk_mapping}")
    print(f" Elapsed Time:        {elapsed_time:.2f} seconds")
    print("=" * 70 + "\n")

    return {
        "status": "success",
        "course_id": valid_course_id,
        "course_name": valid_course_name,
        "lecture_id": valid_lecture_id,
        "lecture_title": valid_lecture_title,
        "transcript_chunks": len(transcript_chunks),
        "pdf_chunks": len(pdf_chunks),
        "total_index_chunks": kb_summary["total_vectors"],
        "lecture_dir": str(lpaths.lecture_dir),
        "raw_audio_path": str(preserved_audio) if preserved_audio else None,
        "raw_pdf_path": str(preserved_pdf) if preserved_pdf else None,
        "dataset_metadata_path": str(lpaths.dataset_metadata),
        "faiss_index_path": str(lpaths.faiss_index),
        "embeddings_path": str(lpaths.embeddings),
        "chunk_mapping_path": str(lpaths.chunk_mapping),
        "lecture_concepts_count": len(dataset_summary.get("lecture_concepts", [])),
        "elapsed_seconds": elapsed_time,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Master Lecture Ingestion Pipeline: Creates an isolated knowledge base under "
            "backend/data/lectures/{course_id}/{lecture_id}/."
        )
    )
    parser.add_argument("--course-id", required=True, help="Course identifier (required, e.g. DBMS).")
    parser.add_argument("--lecture-id", required=True, help="Lecture identifier (required, e.g. DBMS_lect1).")
    parser.add_argument("--course-name", required=True, help="Course display name (required).")
    parser.add_argument("--lecture-title", required=True, help="Lecture display title (required).")
    parser.add_argument(
        "--audio",
        default=None,
        help="Path to lecture audio/video file (.mp3, .mp4, .wav, .m4a). Required unless --pdf-only.",
    )
    parser.add_argument(
        "--pdf",
        default=None,
        help="Path to lecture slides/notes PDF file (.pdf). Required unless --audio-only.",
    )
    parser.add_argument(
        "--audio-only",
        action="store_true",
        help="Explicitly ingest audio only without a PDF file.",
    )
    parser.add_argument(
        "--pdf-only",
        action="store_true",
        help="Explicitly ingest PDF only without an audio file.",
    )
    parser.add_argument(
        "--whisper-model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: base).",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="PyTorch device ('cpu', 'cuda') for Whisper.",
    )
    parser.add_argument(
        "--force-reprocess",
        action="store_true",
        help="Force full re-transcription and re-extraction for this lecture even if cache matches.",
    )
    parser.add_argument(
        "--data-root",
        default=None,
        help="Optional custom data root directory (defaults to backend/data).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.audio_only and args.pdf_only:
        parser.error("Cannot specify both --audio-only and --pdf-only.")
    if not args.audio_only and not args.pdf_only:
        if not args.audio or not args.pdf:
            parser.error("Both --audio and --pdf are required unless --audio-only or --pdf-only is specified.")
    elif args.audio_only and not args.audio:
        parser.error("--audio is required when --audio-only is specified.")
    elif args.pdf_only and not args.pdf:
        parser.error("--pdf is required when --pdf-only is specified.")

    try:
        run_pipeline(
            course_id=args.course_id,
            lecture_id=args.lecture_id,
            course_name=args.course_name,
            lecture_title=args.lecture_title,
            audio_path=args.audio,
            pdf_path=args.pdf,
            audio_only=args.audio_only,
            pdf_only=args.pdf_only,
            whisper_model=args.whisper_model,
            device=args.device,
            force_reprocess=args.force_reprocess,
            data_root=args.data_root,
        )
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
