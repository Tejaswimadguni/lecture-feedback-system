# Lecture Feedback & Verification System

An end-to-end AI lecture verification platform (**React + Vite** frontend and **FastAPI + Python** backend) that analyzes student learning reflections against an instructor's actual lecture audio/video transcripts and slide decks (PDF / PPTX).

The system operates **100% on persistent local storage with NO database**:
- **Authoritative Backend Storage:** Local filesystem (`backend/data/lectures/{subject_id}/{lecture_id}/` and `backend/data/results/{subject_id}/{lecture_id}/` plus `backend/data/workspace_registry.json`).
- **Browser Persistence:** Native **IndexedDB** (`LectureFeedbackSystemIDB`) for navigation context, cached workspace records, uploaded `File`/`Blob` handles, and evaluation result caches—retaining full state across browser refreshes without relying on `localStorage` for files.
- **Strict Lecture Isolation:** Every lecture builds its own independent `all-MiniLM-L6-v2` embeddings and FAISS `IndexFlatIP` knowledge base. Two lectures in the same subject (`DBMS/DBMS_lect1` vs `DBMS/DBMS_lect2`) never share raw files, chunks, embeddings, FAISS indexes, or student evaluation results.

---

## End-to-End Architecture

```text
Teacher Selection -> Subject Management -> Chapter Management -> Lecture Upload
       │
       ▼
Lecture Processing (Whisper + PyMuPDF/python-pptx + Cleaners + Chunkers + Isolated FAISS)
       │
       ▼
Student Feedback CSV Upload (Column Mapping + Duplicate/Collision/Empty Validation + Preview)
       │
       ▼
Verification & Scoring (Claim Extraction -> Lecture-Scoped Retrieval -> Verification -> 10-Mark Rubric)
       │
       ▼
Interactive Results Dashboard (Leaderboard + Student Claim/Evidence Inspector + CSV/JSON Export + ZIP Backup)
```

---

## Local Storage Architecture

```text
lecture-feedback-system/
├── backend/
│   ├── api/                         # FastAPI web layer (no database)
│   │   ├── main.py                  # REST API routes, CORS, error handling
│   │   ├── storage.py               # Local JSON registry, filesystem sync, CSV inspector, ZIP backup
│   │   ├── jobs.py                  # ThreadPoolExecutor background workers + live stage progress
│   │   └── schemas.py               # Pydantic request payloads
│   ├── common/paths.py              # Identifier validation, path resolution, SHA-256 hashing
│   ├── ingestion/                   # Whisper (audio.py), PDF (pdf.py), PPTX (ppt.py)
│   ├── processing/                  # Cleaners, timestamp/page chunkers, dynamic concept derivation
│   ├── retrival/                    # SentenceTransformer + isolated FAISS vector store & search
│   ├── verification/                # Claim extractor, evidence retriever, evaluator, 10-mark scorer
│   ├── main.py                      # Backend server launcher (uvicorn backend.api.main:app)
│   ├── run_lecture_pipeline.py      # Standalone CLI lecture ingestion runner
│   └── data/                        # Authoritative local filesystem storage
│       ├── workspace_registry.json  # Teachers, subjects, chapters & job manifests
│       ├── lectures/
│       │   └── {subject_id}/
│       │       └── {lecture_id}/
│       │           ├── lecture.json
│       │           ├── raw/                 # Preserved audio/video & PDF/PPTX files
│       │           ├── inputs/              # Uploaded student feedback CSV
│       │           ├── processed/           # transcript_{raw,clean,chunks}.json, pdf_{raw,clean,chunks}.json
│       │           ├── metadata/            # dataset_metadata.json (derived lecture concepts)
│       │           └── knowledge_base/      # index.faiss, embeddings.npy, chunk_mapping.json
│       └── results/
│           └── {subject_id}/
│               └── {lecture_id}/
│                   ├── {student_id}/        # claims.json, evidence.json, evaluated.json, score.json
│                   └── all_students_summary.json
├── frontend/                        # React 18 + Vite Teacher Dashboard
│   ├── src/
│   │   ├── api/client.js            # FastAPI REST & file upload client
│   │   ├── storage/indexedDb.js     # Native IndexedDB persistence & Blob store
│   │   ├── components/              # 8-stage Teacher Dashboard views & modals
│   │   └── App.jsx                  # State sync, live background job polling & navigation
│   ├── package.json
│   └── vite.config.js               # Proxies /api -> http://127.0.0.1:8000
├── tests/                           # Automated unit, isolation & E2E API test suites
└── requirements.txt
```

---

## Setup & Running the Full Application

### 1. Backend Setup & Startup (Port `8000`)

```powershell
cd lecture-feedback-system
pip install -r requirements.txt

# Optional: configure .env with GEMINI_API_KEY or OPENROUTER_API_KEY
# (Automatically falls back to deterministic lexical/semantic verification if unavailable)

# Start FastAPI backend
python backend/main.py
# Or with auto-reload:
uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend Setup & Startup (Port `5173`)

Open a second terminal:

```powershell
cd lecture-feedback-system/frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser. Any existing CLI-processed lectures under `backend/data/lectures/` are automatically imported on startup.

---

## CLI Usage (Headless / Scripted Workflows)

### Ingest a Lecture:
```bash
python backend/run_lecture_pipeline.py \
    --course-id DBMS \
    --lecture-id DBMS_lect1 \
    --course-name "Database Management Systems" \
    --lecture-title "Normalization" \
    --audio "path/to/normalization_audio.mp3" \
    --pdf "path/to/normalization_slides.pdf"
```

### Verify Student Feedback CSV:
```bash
python backend/verification/pipeline.py \
    --course-id DBMS \
    --lecture-id DBMS_lect1 \
    --feedback-csv "path/to/student_feedback.csv" \
    --student-id-column roll_number \
    --feedback-column feedback
```

---

## 10-Mark Verification Rubric & Grading

- **Factual Accuracy (`5` marks):** Verified claim accuracy (`SUPPORTED = 1.0`, `PARTIALLY_SUPPORTED = 0.5`, `NOT_SUPPORTED = 0.0`).
- **Lecture Coverage (`3` marks):** Dynamic coverage of the selected lecture's derived concept units (`dataset_metadata.json`).
- **Understanding Quality (`2` marks):** Combines factual precision (`60%`) and verified claim depth (`40%`).
- **Letter Grades:** `A+` (`>= 9.0`), `A` (`>= 8.0`), `B` (`>= 7.0`), `C` (`>= 6.0`), `D` (`>= 5.0`), `F` (`< 5.0`).

---

## Running Automated Tests & Production Build

```powershell
# Run full backend + API E2E test suite
python -m pytest tests -v
python tests/run_tests.py

# Build production frontend bundle
cd frontend
npm run build
```
