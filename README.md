# Lecture Feedback Analysis System

An AI-driven system that analyzes student learning reflections and evaluates whether claimed learning points are genuinely supported by the instructor's lecture materials (audio/video transcripts and lecture slides/notes).

Every lecture maintains a **strictly isolated knowledge base** under `backend/data/lectures/{course_id}/{lecture_id}/`, and every student verification run queries **only** the explicitly specified lecture's knowledge base—preventing any cross-lecture or cross-subject contamination.

---

## Architecture & Pipeline Flow

```
[ Lecture Audio / Video + PDF Slides ]
              │
              ▼
   1. Ingestion & Extraction (Whisper + PyMuPDF / pypdf)
              │
              ▼
   2. Cleaning & Metadata-Rich Chunking (Timestamps & Page Numbers Preserved)
              │
              ▼
   3. Isolated Lecture Knowledge Base (all-MiniLM-L6-v2 + Independent FAISS Index)
              │
              ▼
   4. Dynamic Student Verification & Scoring (Claims -> Lecture FAISS -> Evaluation -> 10-Mark Rubric)
```

---

## Directory Architecture

```text
lecture-feedback-system/
├── backend/
│   ├── common/                  # Shared identifier validation & isolated path resolution
│   │   └── paths.py
│   ├── ingestion/               # Raw audio/video/pdf/ppt extraction modules
│   │   ├── audio.py             # Whisper speech-to-text with chunked processing
│   │   ├── pdf.py               # PDF page-by-page text extractor (PyMuPDF / pypdf)
│   │   └── ppt.py               # PowerPoint slide extractor (python-pptx)
│   ├── processing/              # Cleaning, chunking, metadata & dynamic concept derivation
│   │   ├── pipeline.py          # Lecture processing pipeline
│   │   ├── transcript_cleaner.py# Removes filler words and normalizes speech text
│   │   ├── transcript_chunker.py# Sliding-window timestamp-preserving chunker
│   │   ├── pdf_cleaner.py       # Removes headers/footers, preserves equations
│   │   ├── pdf_chunker.py       # Page-aware slide/document chunker
│   │   └── metadata.py          # Chunk validation & lecture-derived concept extraction
│   ├── retrival/                # Lecture-isolated vector store & semantic search
│   │   ├── embedding.py         # SentenceTransformer wrapper (all-MiniLM-L6-v2)
│   │   ├── vector_store.py      # FAISS IndexFlatIP + strict mapping/vector validation
│   │   ├── build_index.py       # Builds isolated lecture FAISS knowledge base
│   │   └── search.py            # Top-K semantic search scoped to {course_id}/{lecture_id}
│   ├── verification/            # Dynamic student claim verification & scoring
│   │   ├── llm_client.py        # LLM client (Gemini / OpenRouter) with secret redaction
│   │   ├── claims.py            # CSV validation & atomic claim extraction
│   │   ├── retrieve_evidence.py # Matches claims strictly against selected lecture KB
│   │   ├── evaluvator.py        # Evaluates claims vs lecture evidence
│   │   ├── scorer.py            # Dynamic 10-mark rubric (Accuracy /5, Coverage /3, Understanding /2)
│   │   └── pipeline.py          # Master dynamic verification runner
│   ├── data/                    # Dynamically managed per-course / per-lecture storage
│   │   ├── lectures/
│   │   │   └── {course_id}/
│   │   │       └── {lecture_id}/
│   │   │           ├── raw/
│   │   │           │   ├── <audio_file>
│   │   │           │   └── <pdf_file>
│   │   │           ├── processed/
│   │   │           │   ├── transcript_raw.json
│   │   │           │   ├── transcript_clean.json
│   │   │           │   ├── transcript_chunks.json
│   │   │           │   ├── pdf_raw.json
│   │   │           │   ├── pdf_clean.json
│   │   │           │   └── pdf_chunks.json
│   │   │           ├── metadata/
│   │   │           │   └── dataset_metadata.json
│   │   │           └── knowledge_base/
│   │   │               ├── index.faiss
│   │   │               ├── embeddings.npy
│   │   │               └── chunk_mapping.json
│   │   └── results/
│   │       └── {course_id}/
│   │           └── {lecture_id}/
│   │               ├── {student_id}/
│   │               │   ├── claims.json
│   │               │   ├── evidence.json
│   │               │   ├── evaluated.json
│   │               │   └── score.json
│   │               └── all_students_summary.json
│   └── run_lecture_pipeline.py  # Master lecture ingestion CLI
├── tests/                       # Automated unit & isolation test suites
│   ├── run_tests.py
│   ├── test_lecture_isolation_and_verification.py
│   ├── test_metadata.py
│   ├── test_pdf_processing.py
│   ├── test_retrieval.py
│   └── test_transcript_processing.py
├── requirements.txt
└── README.md
```

---

## Installation & Setup

### 1. Create and Activate a Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in `lecture-feedback-system/`:

```env
GEMINI_API_KEY=your_gemini_api_key_here
# Or optionally:
# OPENROUTER_API_KEY=sk-or-v1-...
```

---

## Usage: Lecture Ingestion Pipeline

Every lecture ingestion requires explicit identifiers (`--course-id`, `--lecture-id`, `--course-name`, `--lecture-title`) and explicit input file paths (`--audio`, `--pdf`). No default lecture IDs or filenames are ever assumed.

### Ingest Lecture 1:
```bash
python backend/run_lecture_pipeline.py \
    --course-id DBMS \
    --lecture-id DBMS_lect1 \
    --course-name "Database Management Systems" \
    --lecture-title "Normalization" \
    --audio "data/raw/audio/normalization.mp3" \
    --pdf "data/raw/pdf/normalization.pdf"
```

### Ingest Lecture 2:
```bash
python backend/run_lecture_pipeline.py \
    --course-id DBMS \
    --lecture-id DBMS_lect2 \
    --course-name "Database Management Systems" \
    --lecture-title "SQL Joins" \
    --audio "data/raw/audio/sql_joins.mp3" \
    --pdf "data/raw/pdf/sql_joins.pdf"
```

### Ingestion CLI Flags:
| Argument | Required | Description |
|---|---|---|
| `--course-id <id>` | Yes | Explicit course/subject identifier (e.g. `DBMS`) |
| `--lecture-id <id>` | Yes | Explicit lecture identifier (e.g. `DBMS_lect1`) |
| `--course-name <name>` | Yes | Human-readable course name |
| `--lecture-title <title>` | Yes | Human-readable lecture title |
| `--audio <path>` | Yes* | Path to lecture audio/video (`.mp3`, `.mp4`, `.wav`, `.m4a`, etc.) |
| `--pdf <path>` | Yes* | Path to lecture slides/notes PDF (`.pdf`) |
| `--audio-only` | No | Explicitly run audio-only ingestion without a PDF |
| `--pdf-only` | No | Explicitly run PDF-only ingestion without an audio file |
| `--whisper-model <size>` | No | Whisper model (`tiny`, `base`, `small`, `medium`, `large`; default: `base`) |
| `--device <cpu\|cuda>` | No | PyTorch device for Whisper |
| `--force-reprocess` | No | Force fresh transcription/extraction and replace this lecture's KB |

---

## Usage: Student Feedback Verification Pipeline

Verification requires `--course-id`, `--lecture-id`, and `--feedback-csv`. It resolves `backend/data/lectures/{course_id}/{lecture_id}/knowledge_base/` automatically, verifies integrity before starting, and writes isolated student results under `backend/data/results/{course_id}/{lecture_id}/`.

### Verify Lecture 1 Student Feedback:
```bash
python backend/verification/pipeline.py \
    --course-id DBMS \
    --lecture-id DBMS_lect1 \
    --feedback-csv "data/raw/students/dbms_lect1_feedback.csv"
```

### Verify Lecture 2 Student Feedback:
```bash
python backend/verification/pipeline.py \
    --course-id DBMS \
    --lecture-id DBMS_lect2 \
    --feedback-csv "data/raw/students/dbms_lect2_feedback.csv"
```

### Verification CLI Flags:
| Argument | Required | Description |
|---|---|---|
| `--course-id <id>` | Yes | Course identifier matching the ingested lecture |
| `--lecture-id <id>` | Yes | Lecture identifier matching the ingested lecture |
| `--feedback-csv <path>` | Yes | Path to student feedback `.csv` file |
| `--student-id-column <col>` | No | CSV column for student ID (default: `roll_number`) |
| `--feedback-column <col>` | No | CSV column for student feedback text (default: `feedback`) |
| `--top-k <int>` | No | Top-K lecture chunks retrieved per claim (default: `5`) |
| `--output-dir <path>` | No | Optional custom results output directory |
| `--strict-llm` | No | Fail immediately on missing LLM API credentials or API errors |

---

## Standalone Lecture Semantic Search

Query a specific lecture's isolated knowledge base directly:

```bash
python backend/retrival/search.py \
    --course-id DBMS \
    --lecture-id DBMS_lect1 \
    --query "What does Third Normal Form eliminate?" \
    --top-k 5
```

---

## Scoring Rubric (10 Marks Total)

- **Factual Accuracy (5 marks):** Proportion of student claims verified as `SUPPORTED` (`1.0`) or `PARTIALLY_SUPPORTED` (`0.5`) against retrieved lecture evidence.
- **Lecture Coverage (3 marks):** Proportion of the selected lecture's dynamically derived concept units (`dataset_metadata.json` / lecture chunks) covered by the student's supported claims.
- **Understanding Quality (2 marks):** Combines factual precision and verified claim depth.

---

## Running Tests

```bash
# Run via pytest
pytest tests -v

# Run via standalone test runner
python tests/run_tests.py
```
