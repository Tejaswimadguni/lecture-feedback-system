#!/usr/bin/env python3
"""
Master Lecture Ingestion Pipeline
=================================
Executes the end-to-end ingestion and indexing pipeline for a lecture:
1. Audio transcription via Whisper (audio.py)
2. Transcript cleaning (transcript_cleaner.py)
3. Transcript chunking (transcript_chunker.py)
4. PDF slide/notes text extraction (pdf.py)
5. PDF cleaning (pdf_cleaner.py)
6. PDF page-aware chunking (pdf_chunker.py)
7. Dataset metadata consolidation (metadata.py)
8. Dense embeddings & deduplicated FAISS index updating (embedding.py, vector_store.py)

Usage:
    python backend/run_lecture_pipeline.py \
        --audio data/raw/audio/6100l-lecture-1-version-2_360p_16_9.mp3 \
        --pdf data/raw/pdf/mit6_100l_f22_lec01.pdf \
        --course-id MIT_6_100L \
        --lecture-id lec01
"""

import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("lecture_pipeline")

# Resolve project directories and ensure correct sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RETRIVAL_DIR = PROJECT_ROOT / "backend" / "retrival"
if str(RETRIVAL_DIR) not in sys.path:
    sys.path.insert(0, str(RETRIVAL_DIR))


def _derive_lecture_id_fallback(file_path: str) -> str:
    """Fallback lecture ID derivation without importing heavy modules."""
    basename = os.path.basename(file_path)
    lecture_id, _ = os.path.splitext(basename)
    return lecture_id



def print_stage_banner(stage_num: int, total_stages: int, title: str):
    """Prints a formatted console banner for pipeline stages."""
    print(f"\n{'='*70}")
    print(f" [Stage {stage_num}/{total_stages}] {title.upper()}")
    print(f"{'='*70}")


def run_pipeline(
    audio_path: Optional[str] = None,
    pdf_path: Optional[str] = None,
    course_id: str = "MIT_6_100L",
    lecture_id: Optional[str] = None,
    course_name: str = "Introduction to CS",
    lecture_title: str = "Introduction",
    whisper_model: str = "base",
    device: Optional[str] = None,
    force_rebuild: bool = False,
) -> Dict[str, Any]:
    """
    Executes the entire lecture ingestion and indexing pipeline.
    """
    start_time = time.time()
    total_stages = 5

    # Derive and canonicalize lecture ID if not explicitly specified
    if not lecture_id:
        raw_id = ""
        try:
            from backend.ingestion.audio import derive_lecture_id
        except ImportError:
            derive_lecture_id = _derive_lecture_id_fallback

        if audio_path and os.path.exists(audio_path):
            raw_id = derive_lecture_id(audio_path)
        elif pdf_path and os.path.exists(pdf_path):
            raw_id = derive_lecture_id(pdf_path)

        # Normalize common lecture 1 filenames to canonical 'lec01'
        if any(k in raw_id.lower() for k in ["lec01", "lecture_01", "lecture_1", "lec1", "lec_01", "mit6_100l_f22_lec01"]):
            lecture_id = "lec01"
        elif raw_id:
            lecture_id = raw_id
        else:
            lecture_id = "lec01"

    # Set up directory paths
    transcripts_dir = PROJECT_ROOT / "data" / "processed" / "transcripts"
    pdf_text_dir = PROJECT_ROOT / "data" / "processed" / "pdf_text"
    metadata_dir = PROJECT_ROOT / "data" / "processed" / "metadata"
    vector_store_dir = PROJECT_ROOT / "data" / "vector_store"

    # Auto-create all required directories
    for d in [transcripts_dir, pdf_text_dir, metadata_dir, vector_store_dir]:
        d.mkdir(parents=True, exist_ok=True)

    transcript_chunks: List[Dict[str, Any]] = []
    pdf_chunks: List[Dict[str, Any]] = []

    print("\n" + "#"*70)
    print(" LECTURE FEEDBACK SYSTEM - MASTER INGESTION PIPELINE")
    print("#"*70)
    print(f" Course ID:     {course_id} ({course_name})")
    print(f" Lecture ID:    {lecture_id} ({lecture_title})")
    print(f" Audio Source:  {audio_path if audio_path else '[None]'}")
    print(f" PDF Source:    {pdf_path if pdf_path else '[None]'}")
    print(f" Vector Store:  {vector_store_dir}")

    # =========================================================================
    # STAGE 1 & 2: Audio Ingestion, Cleaning, and Chunking
    # =========================================================================
    if audio_path:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Specified audio file not found: {audio_path}")

        print_stage_banner(1, total_stages, "Audio Ingestion & Whisper Transcription")

        # Check if raw transcript already exists to avoid redundant Whisper transcription
        existing_raw = transcripts_dir / f"{lecture_id}_raw.json"
        if not existing_raw.exists() and (transcripts_dir / "lecture_01_raw.json").exists():
            existing_raw = transcripts_dir / "lecture_01_raw.json"

        if existing_raw.exists() and not force_rebuild:
            logger.info(f"Found existing raw transcript at: {existing_raw}. Reusing transcript (use --force-rebuild to retranscribe).")
            with open(existing_raw, "r", encoding="utf-8") as f:
                transcription_result = json.load(f)
        else:
            logger.info(f"Transcribing audio file: {audio_path} using model '{whisper_model}'...")
            from backend.ingestion.audio import transcribe_audio
            transcription_result = transcribe_audio(
                audio_path=audio_path,
                model_size=whisper_model,
                lecture_id=lecture_id,
                device=device,
            )

        raw_segments = transcription_result.get("segments", [])
        logger.info(f"Loaded {len(raw_segments)} raw transcript segments.")

        # Save raw transcript
        raw_out_path = transcripts_dir / f"{lecture_id}_raw.json"
        with open(raw_out_path, "w", encoding="utf-8") as f:
            json.dump(transcription_result, f, indent=2, ensure_ascii=False)
        # Compatibility copy
        with open(transcripts_dir / "lecture_01_raw.json", "w", encoding="utf-8") as f:
            json.dump(transcription_result, f, indent=2, ensure_ascii=False)

        print_stage_banner(2, total_stages, "Transcript Cleaning & Semantic Chunking")
        from backend.processing.transcript_cleaner import clean_transcript
        from backend.processing.transcript_chunker import chunk_transcript

        cleaned_segments = clean_transcript(raw_segments)
        logger.info(f"Cleaned {len(cleaned_segments)} segments (noise and filler words stripped).")

        clean_out_path = transcripts_dir / f"{lecture_id}_clean.json"
        clean_data = {
            "lecture_id": lecture_id,
            "segments": cleaned_segments
        }
        with open(clean_out_path, "w", encoding="utf-8") as f:
            json.dump(clean_data, f, indent=2, ensure_ascii=False)
        if lecture_id == "lec01":
            with open(transcripts_dir / "lecture_01_clean.json", "w", encoding="utf-8") as f:
                json.dump(clean_data, f, indent=2, ensure_ascii=False)

        transcript_chunks = chunk_transcript(
            segments=cleaned_segments,
            course_id=course_id,
            lecture_id=lecture_id,
            target_word_count=350,
            overlap_word_count=50,
            course_name=course_name,
            lecture_title=lecture_title,
            source_file=os.path.basename(audio_path),
        )
        logger.info(f"Constructed {len(transcript_chunks)} transcript chunks.")

        chunks_out_path = transcripts_dir / f"{lecture_id}_chunks.json"
        with open(chunks_out_path, "w", encoding="utf-8") as f:
            json.dump(transcript_chunks, f, indent=2, ensure_ascii=False)
        # Compatibility alias for build_index.py and verification
        with open(transcripts_dir / "lecture_01_chunks.json", "w", encoding="utf-8") as f:
            json.dump(transcript_chunks, f, indent=2, ensure_ascii=False)

    else:
        print_stage_banner(1, total_stages, "Audio Ingestion (Skipped - No Audio Provided)")
        print_stage_banner(2, total_stages, "Transcript Chunking (Skipped)")

    # =========================================================================
    # STAGE 3: PDF Extraction, Cleaning, and Chunking
    # =========================================================================
    if pdf_path:
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"Specified PDF file not found: {pdf_path}")

        print_stage_banner(3, total_stages, "PDF Extraction, Cleaning & Page-Aware Chunking")
        from backend.ingestion.pdf import extract_pdf_text
        from backend.processing.pdf_cleaner import clean_pdf_pages
        from backend.processing.pdf_chunker import chunk_pdf

        logger.info(f"Extracting text from PDF: {pdf_path}...")
        pdf_raw_data = extract_pdf_text(pdf_path=pdf_path, lecture_id=lecture_id)
        raw_pages = pdf_raw_data.get("pages", [])
        logger.info(f"Extracted {len(raw_pages)} pages.")

        # Save raw PDF text
        pdf_raw_out = pdf_text_dir / f"{lecture_id}_raw.json"
        with open(pdf_raw_out, "w", encoding="utf-8") as f:
            json.dump(pdf_raw_data, f, indent=2, ensure_ascii=False)
        if lecture_id == "lec01":
            with open(pdf_text_dir / "lecture_01_raw.json", "w", encoding="utf-8") as f:
                json.dump(pdf_raw_data, f, indent=2, ensure_ascii=False)

        # Clean PDF pages
        cleaned_pages = clean_pdf_pages(raw_pages)
        logger.info(f"Cleaned {len(cleaned_pages)} pages (headers/footers stripped).")

        pdf_clean_out = pdf_text_dir / f"{lecture_id}_clean.json"
        pdf_clean_data = {
            "lecture_id": lecture_id,
            "pages": cleaned_pages
        }
        with open(pdf_clean_out, "w", encoding="utf-8") as f:
            json.dump(pdf_clean_data, f, indent=2, ensure_ascii=False)
        if lecture_id == "lec01":
            with open(pdf_text_dir / "lecture_01_clean.json", "w", encoding="utf-8") as f:
                json.dump(pdf_clean_data, f, indent=2, ensure_ascii=False)

        # Chunk PDF
        pdf_chunks = chunk_pdf(
            pages=cleaned_pages,
            course_id=course_id,
            lecture_id=lecture_id,
            target_word_count=350,
            course_name=course_name,
            lecture_title=lecture_title,
            source_file=os.path.basename(pdf_path),
        )
        logger.info(f"Constructed {len(pdf_chunks)} PDF chunks.")

        pdf_chunks_out = pdf_text_dir / f"{lecture_id}_chunks.json"
        with open(pdf_chunks_out, "w", encoding="utf-8") as f:
            json.dump(pdf_chunks, f, indent=2, ensure_ascii=False)
        with open(pdf_text_dir / "lecture_01_chunks.json", "w", encoding="utf-8") as f:
            json.dump(pdf_chunks, f, indent=2, ensure_ascii=False)

    else:
        print_stage_banner(3, total_stages, "PDF Extraction & Chunking (Skipped - No PDF Provided)")

    # =========================================================================
    # STAGE 4: Metadata Validation & Dataset Consolidation
    # =========================================================================
    print_stage_banner(4, total_stages, "Metadata Validation & Dataset Summary")
    from backend.processing.metadata import build_dataset_metadata, validate_chunk

    new_lecture_chunks = transcript_chunks + pdf_chunks
    if not new_lecture_chunks:
        raise ValueError("No chunks were generated! Please provide at least one valid audio or PDF file.")

    for chunk in new_lecture_chunks:
        validate_chunk(chunk)

    dataset_summary_path = metadata_dir / "dataset_metadata.json"
    dataset_summary = build_dataset_metadata(new_lecture_chunks, output_path=str(dataset_summary_path))
    logger.info(f"Consolidated dataset metadata saved to {dataset_summary_path}")

    # =========================================================================
    # STAGE 5: Dense Embeddings & Deduplicated FAISS Vector Store Update
    # =========================================================================
    print_stage_banner(5, total_stages, "Dense Embeddings & FAISS Vector Indexing")
    import numpy as np
    # pyrefly: ignore [missing-import]
    from embedding import generate_embeddings
    # pyrefly: ignore [missing-import]
    from vector_store import create_faiss_index, save_faiss_index

    mapping_file = vector_store_dir / "chunk_mapping.json"
    faiss_file = vector_store_dir / "lecture_index.faiss"
    embeddings_file = vector_store_dir / "embeddings.npy"

    existing_mapping: List[Dict[str, Any]] = []
    if mapping_file.exists() and not force_rebuild:
        try:
            with open(mapping_file, "r", encoding="utf-8") as f:
                existing_mapping = json.load(f)
            logger.info(f"Found existing vector store with {len(existing_mapping)} chunks.")
        except Exception as e:
            logger.warning(f"Could not read existing mapping file, initializing fresh: {e}")
            existing_mapping = []

    # Filter out prior chunks for this lecture to prevent duplication
    retained_chunks = [
        c for c in existing_mapping
        if c.get("lecture_id") != lecture_id
    ]
    removed_count = len(existing_mapping) - len(retained_chunks)
    if removed_count > 0:
        logger.info(f"Deduplication: Replaced {removed_count} existing chunks for lecture '{lecture_id}'.")

    # Combine retained chunks from other lectures with newly processed chunks
    combined_chunks = retained_chunks + new_lecture_chunks
    logger.info(f"Total unified chunks for FAISS index: {len(combined_chunks)}")

    # Extract clean text for embedding
    texts = [c.get("text", "").strip() for c in combined_chunks if c.get("text", "").strip()]
    valid_chunks = [c for c in combined_chunks if c.get("text", "").strip()]

    logger.info(f"Generating dense vector embeddings for {len(texts)} chunks using all-MiniLM-L6-v2...")
    embeddings = generate_embeddings(texts)
    logger.info(f"Generated embeddings matrix of shape: {embeddings.shape}")

    # Create & save updated FAISS index
    index = create_faiss_index(embeddings)
    save_faiss_index(index, str(faiss_file))
    logger.info(f"Saved FAISS index to {faiss_file}")

    # Save embeddings array
    np.save(str(embeddings_file), embeddings)
    logger.info(f"Saved embedding vectors to {embeddings_file}")

    # Build synced mapping with 0-indexed vector IDs matching FAISS rows
    updated_mapping = []
    for idx, chunk in enumerate(valid_chunks):
        updated_mapping.append({
            "vector_id": idx,
            "chunk_id": chunk["chunk_id"],
            "course_id": chunk.get("course_id", course_id),
            "lecture_id": chunk.get("lecture_id", lecture_id),
            "source_type": chunk["source_type"],
            "source_file": chunk.get("source_file", ""),
            "page": chunk.get("page"),
            "start_time": chunk.get("start_time"),
            "end_time": chunk.get("end_time"),
            "text": chunk["text"]
        })

    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(updated_mapping, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved chunk mapping ({len(updated_mapping)} entries) to {mapping_file}")

    elapsed_time = time.time() - start_time
    print("\n" + "="*70)
    print(" PIPELINE COMPLETED SUCCESSFULLY!")
    print("="*70)
    print(f" Processed Lecture:    {lecture_id}")
    print(f" New Chunks Added:     {len(new_lecture_chunks)} (Transcript: {len(transcript_chunks)}, PDF: {len(pdf_chunks)})")
    print(f" Total Vector Index:   {len(updated_mapping)} chunks")
    print(f" Elapsed Time:         {elapsed_time:.2f} seconds")
    print(f" FAISS Index Path:     {faiss_file}")
    print(f" Chunk Mapping Path:   {mapping_file}")
    print("\nNext step: Run verification or semantic search:")
    print("  python backend/retrival/search.py")
    print("  python backend/verification/claims.py")
    print("="*70 + "\n")

    return {
        "status": "success",
        "lecture_id": lecture_id,
        "transcript_chunks": len(transcript_chunks),
        "pdf_chunks": len(pdf_chunks),
        "total_index_chunks": len(updated_mapping),
        "elapsed_seconds": elapsed_time,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Master Lecture Ingestion Pipeline: Audio -> Transcript -> PDF -> Chunks -> FAISS Vector Store."
    )
    parser.add_argument(
        "--audio",
        type=str,
        default=None,
        help="Path to the lecture audio/video file (e.g. .mp3, .mp4, .wav)."
    )
    parser.add_argument(
        "--pdf",
        type=str,
        default=None,
        help="Path to the lecture notes or slides PDF file."
    )
    parser.add_argument(
        "--course-id",
        type=str,
        default="MIT_6_100L",
        help="Course identifier (default: MIT_6_100L)."
    )
    parser.add_argument(
        "--lecture-id",
        type=str,
        default=None,
        help="Lecture identifier (default: auto-derived from input file or 'lec01')."
    )
    parser.add_argument(
        "--course-name",
        type=str,
        default="Introduction to CS",
        help="Course display name."
    )
    parser.add_argument(
        "--lecture-title",
        type=str,
        default="Introduction",
        help="Lecture display title."
    )
    parser.add_argument(
        "--whisper-model",
        type=str,
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: base)."
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="PyTorch device ('cpu', 'cuda') for Whisper and SentenceTransformer."
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Rebuild the vector store from scratch instead of deduplicated incremental merge."
    )

    args = parser.parse_args()

    audio_arg = args.audio
    pdf_arg = args.pdf

    # Auto-discover audio if not explicitly provided
    if not audio_arg:
        audio_candidates = [
            PROJECT_ROOT / "data" / "raw" / "audio" / "lecture_01.mp3",
            PROJECT_ROOT / "data" / "raw" / "audio" / "6100l-lecture-1-version-2_360p_16_9.mp3",
            PROJECT_ROOT / "data" / "raw" / "audio" / "lecture_01.mp4",
            PROJECT_ROOT / "data" / "raw" / "audio" / "lecture_01.wav",
        ]
        for cand in audio_candidates:
            if cand.exists():
                audio_arg = str(cand)
                break
        if not audio_arg:
            audio_dir = PROJECT_ROOT / "data" / "raw" / "audio"
            if audio_dir.exists():
                for ext in ["*.mp3", "*.mp4", "*.wav", "*.m4a"]:
                    found = list(audio_dir.glob(ext))
                    if found:
                        audio_arg = str(found[0])
                        break

    # Auto-discover PDF if not explicitly provided
    if not pdf_arg:
        pdf_candidates = [
            PROJECT_ROOT / "data" / "raw" / "pdf" / "mit6_100l_f22_lec01.pdf",
            PROJECT_ROOT / "data" / "raw" / "pdf" / "lecture_01.pdf",
        ]
        for cand in pdf_candidates:
            if cand.exists():
                pdf_arg = str(cand)
                break
        if not pdf_arg:
            pdf_dir = PROJECT_ROOT / "data" / "raw" / "pdf"
            if pdf_dir.exists():
                found_pdfs = list(pdf_dir.glob("*.pdf"))
                if found_pdfs:
                    pdf_arg = str(found_pdfs[0])

    if not audio_arg and not pdf_arg:
        parser.error("No input files found. Please provide at least one of --audio or --pdf file paths.")

    try:
        run_pipeline(
            audio_path=audio_arg,
            pdf_path=pdf_arg,
            course_id=args.course_id,
            lecture_id=args.lecture_id,
            course_name=args.course_name,
            lecture_title=args.lecture_title,
            whisper_model=args.whisper_model,
            device=args.device,
            force_rebuild=args.force_rebuild,
        )
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
