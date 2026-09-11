# Backend Architecture

Python-based processing, retrieval, and verification engine for the Lecture Feedback Analysis System.

## Architecture Modules

- **`ingestion/`**: Audio, video, PDF, and PowerPoint ingestion. Uses OpenAI Whisper for speech-to-text and PyMuPDF / pypdf / python-pptx for slide extraction.
- **`processing/`**: Text cleaning, filler word normalization, sliding-window chunking, and metadata schema validation.
- **`retrival/`**: Dense text embedding generation (`sentence-transformers` with `all-MiniLM-L6-v2`) and cosine similarity indexing using FAISS.
- **`verification/`**: Student claim extraction from CSV reflections, FAISS evidence retrieval, Google Gemini LLM factual verification, and multi-factor scoring.

## Quick Commands

From the project root:

```bash
# Ingestion & Chunking
python backend/ingestion/audio.py --audio data/raw/audio/6100l-lecture-1-version-2_360p_16_9.mp3
python backend/ingestion/pdf.py --pdf data/raw/pdf/mit6_100l_f22_lec01.pdf
python backend/processing/pipeline.py

# Retrieval Indexing
python backend/retrival/build_index.py

# Feedback Verification Pipeline
python backend/verification/claims.py
python backend/verification/retrieve_evidence.py
python backend/verification/evaluvator.py
python backend/verification/scorer.py
```

For complete setup, environment configuration, and test instructions, refer to the [Root README](../README.md).
