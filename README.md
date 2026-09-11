# Lecture Feedback Analysis System

An AI-driven system that analyzes student learning reflections and evaluates whether claimed learning points are genuinely supported by the instructor's lecture materials (audio/video transcripts and lecture slides/notes).

---

## Architecture & Pipeline Flow

The system processes data across four sequential stages:

```
[ Lecture Audio / Video / PDF ]
              │
              ▼
   1. Ingestion & Extraction (Whisper, PyMuPDF, python-pptx)
              │
              ▼
   2. Processing & Chunking (Noise cleaning, sliding window, metadata)
              │
              ▼
   3. Vector Indexing & Retrieval (all-MiniLM-L6-v2 + FAISS)
              │
              ▼
   4. Verification & Scoring (Gemini LLM claim extraction, evidence matching & multi-factor scoring)
```

---

## Project Structure

```text
lecture-feedback-system/
├── backend/
│   ├── ingestion/               # Raw audio/video/pdf/ppt ingestion scripts
│   │   ├── audio.py             # Whisper speech-to-text with chunked processing
│   │   ├── pdf.py               # PDF text extractor (PyMuPDF / pypdf)
│   │   └── ppt.py               # PowerPoint slide extractor (python-pptx)
│   ├── processing/              # Cleaning, chunking, and dataset metadata
│   │   ├── pipeline.py          # End-to-end processing pipeline
│   │   ├── transcript_cleaner.py# Removes filler words and normalizes speech text
│   │   ├── transcript_chunker.py# Sliding-window timestamp-aware chunker
│   │   ├── pdf_cleaner.py       # Removes headers/footers, preserves equations
│   │   ├── pdf_chunker.py       # Page-aware slide/document chunker
│   │   └── metadata.py          # Chunk metadata schemas and validation
│   ├── retrival/                # Vector store and semantic search
│   │   ├── embedding.py         # SentenceTransformer wrapper (all-MiniLM-L6-v2)
│   │   ├── vector_store.py      # FAISS IndexFlatIP (cosine similarity) helper
│   │   ├── build_index.py       # Builds FAISS index from processed chunks
│   │   └── search.py            # Top-K semantic similarity search
│   └── verification/            # Student feedback verification & LLM evaluation
│       ├── claims.py            # Extracts atomic claims from student reflections
│       ├── retrieve_evidence.py # Matches claims to lecture chunks via FAISS
│       ├── evaluvator.py        # Evaluates claims vs evidence using Google Gemini
│       ├── scorer.py            # Multi-factor scoring (accuracy, coverage, depth)
│       └── test_gemini.py       # Quick sanity test for Gemini API connectivity
├── data/
│   ├── raw/                     # Original lecture audio, pdf, video, student CSVs
│   ├── processed/               # Cleaned texts, JSON chunks, dataset summaries
│   ├── vector_store/            # FAISS index (.faiss) and chunk mappings (.json)
│   └── results/                 # Evaluation outputs, evidence matches, scores
├── tests/                       # Unit and integration test suites
│   ├── run_tests.py             # Test runner
│   ├── test_metadata.py
│   ├── test_pdf_processing.py
│   └── test_transcript_processing.py
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Prerequisites

- **Python 3.10+** (Python 3.10 - 3.12 recommended)
- **Git**
- **Google Gemini API Key** (Required for verification stage)
  - Get an API key from [Google AI Studio](https://aistudio.google.com/)

---

## Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/Tejaswimadguni/lecture-feedback-system.git
cd lecture-feedback-system
```

### 2. Create and Activate a Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **Note on FFmpeg:** Whisper relies on FFmpeg for audio decoding. `imageio-ffmpeg` is included in `requirements.txt` to provide a pre-compiled FFmpeg binary automatically. If you prefer using system FFmpeg, install it via `winget install Gyan.FFmpeg` (Windows) or `brew install ffmpeg` (macOS).

### 4. Configure Environment Variables

Create a `.env` file in the project root or export `GEMINI_API_KEY`:

**In `.env`:**
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

**Or export directly:**
- **Windows (PowerShell):** `$env:GEMINI_API_KEY="your_api_key_here"`
- **Windows (CMD):** `set GEMINI_API_KEY=your_api_key_here`
- **Linux / macOS:** `export GEMINI_API_KEY="your_api_key_here"`

---

## Step-by-Step Pipeline Execution

Run all commands from the root directory of the repository:

### Step 1: Ingestion (Extract text from audio and slides)

Extract lecture transcript from audio:
```bash
python backend/ingestion/audio.py --audio data/raw/audio/6100l-lecture-1-version-2_360p_16_9.mp3
```

Extract lecture notes from PDF:
```bash
python backend/ingestion/pdf.py --pdf data/raw/pdf/mit6_100l_f22_lec01.pdf
```

*(Optional)* Extract from PowerPoint (.pptx):
```bash
python backend/ingestion/ppt.py --ppt path/to/lecture.pptx
```

---

### Step 2: Processing & Chunking

Clean the raw transcript and PDF texts, generate time-stamped / page-aware chunks, and produce dataset metadata:
```bash
python backend/processing/pipeline.py
```
Outputs generated in `data/processed/`:
- `data/processed/transcripts/lecture_01_chunks.json`
- `data/processed/pdf_text/lecture_01_chunks.json`
- `data/processed/metadata/dataset_metadata.json`

---

### Step 3: Vector Store & Semantic Retrieval

#### A. Build the FAISS Index
Generate dense vector embeddings (`all-MiniLM-L6-v2`) and build the FAISS index:
```bash
python backend/retrival/build_index.py
```
This saves:
- `data/vector_store/lecture_index.faiss`
- `data/vector_store/chunk_mapping.json`

#### B. Test Semantic Search
Verify that queries retrieve relevant lecture chunks:
```bash
python backend/retrival/search.py
```

---

### Step 4: Student Verification & LLM Evaluation

#### A. Sanity Check Gemini API
Verify your Gemini API credentials:
```bash
python backend/verification/test_gemini.py
```

#### B. Extract Student Claims
Parse student reflections from `data/raw/students/lecture_feedback_25_students.csv` into atomic factual claims:
```bash
python backend/verification/claims.py
```
Output: `data/results/student_01_claims.json`

#### C. Retrieve Lecture Evidence
Query the FAISS vector index to find the most relevant chunks for each extracted claim:
```bash
python backend/verification/retrieve_evidence.py
```
Output: `data/results/student_01_evidence.json`

#### D. Evaluate Claims with LLM
Use Gemini to evaluate whether each claim is **Supported**, **Partially Supported**, or **Unsupported** by the retrieved lecture evidence:
```bash
python backend/verification/evaluvator.py
```
Output: `data/results/student_01_evaluated.json`

#### E. Calculate Final Verification Scores
Compute accuracy, coverage, and understanding depth scores:
```bash
python backend/verification/scorer.py
```
Output: `data/results/student_01_score.json`

---

## Running Tests

Run the test suite with either `pytest` or the standalone runner:

```bash
# Using pytest
pytest

# Using standalone runner
python tests/run_tests.py
```

---

## Troubleshooting

1. **`ModuleNotFoundError: No module named 'sentence_transformers'` or `faiss`**
   - Ensure your virtual environment is activated and run:
     ```bash
     pip install -r requirements.txt
     ```
2. **`ValueError: GEMINI_API_KEY is not set`**
   - Make sure `GEMINI_API_KEY` is exported in your terminal or present in `.env`.
3. **`FileNotFoundError: data/processed/.../lecture_01_chunks.json`**
   - Run `python backend/processing/pipeline.py` before building the vector index.
4. **`FileNotFoundError: data/vector_store/lecture_index.faiss`**
   - Run `python backend/retrival/build_index.py` before running evidence retrieval.
5. **Import errors when running scripts**
   - Always run commands from the repository root directory (e.g. `python backend/retrival/build_index.py`).
