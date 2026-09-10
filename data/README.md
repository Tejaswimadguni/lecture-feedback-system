# Data, Audio Transcription, and Teaching Knowledge Base

This folder contains the source material and generated artifacts used by the
Lecture Feedback Analysis and Learning Alignment System. The pipeline is local:
it transcribes lecture media with faster-whisper, preserves source evidence,
creates embeddings, and supports evidence-aware retrieval.

## First-time setup

From the repository root (`lecture-feedback-system`), create and activate a
virtual environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The first run of faster-whisper downloads the selected local Whisper model; the
first run of Sentence Transformers downloads `all-MiniLM-L6-v2`. After those
downloads, both models are cached locally. No OpenAI API key or cloud
transcription service is used.

FFmpeg should be installed and available on `PATH` for reliable media-duration
detection and broad audio/video format support. For example on Windows:

```powershell
winget install Gyan.FFmpeg
```

Close and reopen the terminal after installing FFmpeg so its `bin` directory is
available on `PATH`.

## Data layout

```text
data/
├── raw/
│   ├── audio/                 # Input .mp3, .wav, .m4a, .flac, etc.
│   └── video/                 # Input .mp4, .mkv, .webm, etc.
└── processed/
    ├── transcripts/           # Timestamped faster-whisper JSON transcripts
    ├── pdf_text/              # Extracted PDF text, preserving page numbers
    ├── knowledge_base/
    │   └── <lecture_id>/      # Evidence, knowledge, embeddings, reports
    └── vector_store/
        └── <lecture_id>/      # Searchable evidence and knowledge vectors
```

Do not edit or delete raw files, transcript JSON, or PDF extraction JSON after
they have been generated. They are the authoritative source evidence.

## 1. Transcribe lecture audio or video

Place the media file in `data/raw/audio/` or `data/raw/video/`, then run:

```powershell
python backend/ingestion/audio.py data/raw/audio/lecture.mp3 --model base --device cpu --compute-type int8
```

The default configuration is local CPU transcription using faster-whisper:

```text
Model:        base
Device:       cpu
Compute type: int8
Beam size:    5
```

The transcript is saved as:

```text
data/processed/transcripts/<lecture_filename>_transcript.json
```

Transcript schema:

```json
{
  "lecture_id": "lecture_name",
  "segments": [
    {
      "start": 0.0,
      "end": 5.2,
      "text": "Professor speech from this timestamp range."
    }
  ]
}
```

Long recordings are passed directly to faster-whisper. The pipeline does not
create temporary three-minute WAV files, so timestamps remain relative to the
original lecture.

## 2. Add PDF extraction output

PDF extraction output belongs in `data/processed/pdf_text/`. The current
knowledge-base builder expects this shape:

```json
{
  "lecture_id": "source_lecture_name",
  "pages": [
    { "page": 1, "text": "Text extracted from page 1." }
  ]
}
```

The transcript and PDF may have different source IDs. When that happens, use
explicit file paths in the build command and choose one project-level
`--lecture-id`; this prevents accidental mixing of unrelated lectures.

## 3. Build the Teaching Knowledge Base

Run this from the repository root. Replace paths and `lecture01` with the
lecture you are building:

```powershell
python backend/knowledge/build_kb.py --lecture-id lecture01 --transcript data/processed/transcripts/6100l-lecture-1-version-2_360p_16_9_transcript.json --pdf data/processed/pdf_text/mit6_100l_f22_lec01_notes.json
```

The builder creates two linked layers:

1. **Evidence layer** — deterministic merged audio chunks and page-level PDF
   chunks. It preserves the original text, source file, audio timestamps, PDF
   pages, source type, and lecture ID.
2. **Knowledge layer** — conservative source-grounded concept records. Each
   record has an extractive teaching statement and one or more
   `evidence_chunk_ids`. It never replaces the evidence text.

The authority order is always:

```text
RAW SOURCE > EVIDENCE CHUNK > KNOWLEDGE UNIT > EMBEDDING SCORE
```

An embedding similarity score finds candidates; it is never proof that a
student claim is true. Downstream verification must inspect the returned
original evidence.

## Generated files

For `lecture01`, the build produces:

```text
data/processed/knowledge_base/lecture01/
├── kb.json                    # Backward-compatible evidence layer
├── evidence.json              # Evidence chunks with document_type=evidence
├── metadata.json              # Evidence metadata in embedding order
├── embeddings.npy             # Evidence embeddings
├── knowledge_units.json       # Concepts linked to evidence_chunk_ids
├── knowledge_embeddings.npy   # Knowledge-unit embeddings
├── manifest.json              # Build counts, sources, model, validation status
└── validation_report.json     # Source, evidence, knowledge, and vector checks

data/processed/vector_store/lecture01/
├── vectors.npy                # Evidence vectors
├── metadata.json              # Evidence metadata
└── knowledge/
    ├── vectors.npy            # Knowledge vectors
    └── metadata.json          # Knowledge-unit metadata
```

FAISS is used automatically if installed; otherwise retrieval uses the
included normalized NumPy cosine-similarity fallback.

## 4. Validate the KB

```powershell
python backend/knowledge/validate_kb.py --lecture-id lecture01 --transcript data/processed/transcripts/6100l-lecture-1-version-2_360p_16_9_transcript.json --pdf data/processed/pdf_text/mit6_100l_f22_lec01_notes.json
```

Validation checks source reconstruction, timestamps, page preservation,
lecture isolation, empty/duplicate chunks, knowledge-to-evidence references,
embedding count/dimension, NaN/Inf values, and vector/metadata ordering.

## 5. Search the KB

Search knowledge units first (default):

```powershell
python backend/retrival/search.py "What did the professor teach about assignment?" --lecture-id lecture01 --document-type knowledge --top-k 5
```

Search raw evidence chunks directly when needed:

```powershell
python backend/retrival/search.py "What did the professor teach about assignment?" --lecture-id lecture01 --document-type evidence --top-k 5
```

Knowledge search returns concept records and `evidence_chunk_ids`. Use those
IDs to retrieve the corresponding entries in `evidence.json`/`kb.json`, where
the authoritative original text and timestamp/page are stored.

## 6. Run retrieval diagnostics and tests

```powershell
python backend/knowledge/evaluate_retrieval.py --lecture-id lecture01 --top-k 5
python -m pytest tests/test_knowledge_pipeline.py -q
```

The retrieval evaluator uses source-grounded Lecture 1 queries and reports
Top-1, Top-3, Top-5, MRR, every ranked result, concept, source type, evidence
chunk ID, timestamp/page metadata, and a source-derived excerpt.

## Important rules for contributors

- Do not overwrite raw sources or processed transcript/PDF source files.
- Do not remove timestamps or page numbers.
- Do not treat PDF-only evidence as proof of what was spoken in the lecture.
- Do not add outside facts to knowledge units.
- Do not use an embedding score as a verification verdict.
- Build each lecture under a unique `lecture_id` to keep vector stores isolated.
- Re-run the build and validation whenever source inputs or KB-building code
  changes.
