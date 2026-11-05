# Backend Architecture

Python-based ingestion, processing, isolated vector retrieval, and student verification engine for the Lecture Feedback Analysis System.

## Modules

- **`common/paths.py`**: Strict identifier validation, student ID sanitization, SHA-256 fingerprinting, and dynamic path construction under `backend/data/lectures/{course_id}/{lecture_id}/` and `backend/data/results/{course_id}/{lecture_id}/`.
- **`ingestion/`**: Audio/video transcription via OpenAI Whisper (`audio.py`) and slide/notes extraction via PyMuPDF / pypdf / python-pptx (`pdf.py`, `ppt.py`).
- **`processing/`**: Speech/PDF text cleaning, timestamp-aware and page-aware chunking, schema validation, and lecture-specific concept unit derivation (`metadata.py`).
- **`retrival/`**: `all-MiniLM-L6-v2` dense embeddings (`embedding.py`), per-lecture FAISS `IndexFlatIP` management with vector-to-mapping integrity checks (`vector_store.py`, `build_index.py`), and lecture-scoped search (`search.py`).
- **`verification/`**: Validated CSV ingestion & claim extraction (`claims.py`), isolated lecture evidence retrieval (`retrieve_evidence.py`), LLM claim evaluation (`evaluvator.py`), dynamic 10-mark lecture-specific scoring (`scorer.py`), and end-to-end orchestration (`pipeline.py`).

## Commands

### Ingest a Lecture
```bash
python backend/run_lecture_pipeline.py \
    --course-id DBMS \
    --lecture-id DBMS_lect1 \
    --course-name "Database Management Systems" \
    --lecture-title "Normalization" \
    --audio "data/raw/audio/normalization.mp3" \
    --pdf "data/raw/pdf/normalization.pdf"
```

### Verify Student Feedback for a Lecture
```bash
python backend/verification/pipeline.py \
    --course-id DBMS \
    --lecture-id DBMS_lect1 \
    --feedback-csv "data/raw/students/dbms_lect1_feedback.csv"
```

### Search a Lecture Knowledge Base
```bash
python backend/retrival/search.py \
    --course-id DBMS \
    --lecture-id DBMS_lect1 \
    --query "functional dependencies"
```

Refer to the [Root README](../README.md) for full setup and testing documentation.
