# Lecture Feedback Analysis System

A system that analyzes student learning reflections and checks whether the claimed learning is supported by the professor's lecture materials.

## Project Goal

The system compares what a student says they learned with what was actually taught during the selected time period using transcript timestamps and slide page references.

---

## ⚙️ Prerequisites & Python Version

> **Important**: This project uses **OpenAI Whisper** and **PyTorch**, which require **Python 3.10 or 3.11**.
> On Windows systems with multiple Python versions (e.g., Python 3.14 and 3.11), use the `py -3.11` launcher instead of plain `python`.

### Step 1: Clone the Repository
```bash
git clone <repository_url>
cd lecture-feedback-system
```

### Step 2: Install Dependencies

- **Standard setup (single Python 3.10/3.11 installed):**
  ```bash
  pip install -r requirements.txt
  ```

- **If you have multiple Python versions installed on your machine:**
  ```bash
  py -3.11 -m pip install -r requirements.txt
  ```

---

## 🎧 Audio & Video Ingestion (`backend/ingestion/audio.py`)

Converts lecture audio/video files (`.mp3`, `.mp4`, `.wav`, `.m4a`) into timestamped JSON transcripts saved in `data/processed/transcripts/`.

### 1. Transcribe Any Single Lecture (Lecture 1, Lecture 2, Lecture 3, etc.)

Place your audio or video file inside `data/raw/audio/` or `data/raw/video/`, then run:

```bash
# Standard command:
python backend/ingestion/audio.py data/raw/audio/lecture_01.mp3 --lecture-id lecture_01

# For Lecture 2:
python backend/ingestion/audio.py data/raw/audio/lecture_02.mp4 --lecture-id lecture_02

# For Lecture 3:
python backend/ingestion/audio.py data/raw/audio/lecture_03.mp3 --lecture-id lecture_03
```

*(If your machine has multiple Python versions installed, replace `python` with `py -3.11`)*:
```bash
py -3.11 backend/ingestion/audio.py data/raw/audio/lecture_02.mp4 --lecture-id lecture_02
```

---

### 2. Batch Transcribe All Lectures in One Command (`--all`)

If you have multiple lecture files in `data/raw/audio/` (e.g. `lecture_01.mp3`, `lecture_02.mp4`, `lecture_03.mp3`), you can transcribe all of them automatically in a single run:

```bash
# Standard:
python backend/ingestion/audio.py --all

# With multiple Python versions:
py -3.11 backend/ingestion/audio.py --all
```

---

### 3. Fast Mode (`--model tiny`)

By default, the script uses the `base` model. For **3x to 4x faster transcription** on CPU:

```bash
python backend/ingestion/audio.py data/raw/audio/lecture_02.mp4 --lecture-id lecture_02 --model tiny
# Or batch process all fast:
python backend/ingestion/audio.py --all --model tiny
```

---

### 4. Output Transcript Format

Transcripts are automatically written to `data/processed/transcripts/<lecture_id>_transcript.json`:

```json
{
  "lecture_id": "lecture_01",
  "segments": [
    {
      "start": 0.0,
      "end": 23.6,
      "text": "All right, so welcome to the first lecture of 600L..."
    },
    {
      "start": 23.6,
      "end": 29.12,
      "text": "is Anna Bell. That's two separate names..."
    }
  ]
}
```

---

## 📄 PDF & Slide Ingestion (`backend/ingestion/pdf.py` & `ppt.py`)

### Transcribe PDF Lecture Slides/Notes:
```bash
python backend/ingestion/pdf.py data/raw/pdf/lecture_01.pdf
# (or: py -3.11 backend/ingestion/pdf.py data/raw/pdf/lecture_01.pdf)
```
Output saved to: `data/processed/pdf_text/lecture_01_notes.json`

### Transcribe PowerPoint Slides (`.pptx`):
```bash
python backend/ingestion/ppt.py data/raw/ppt/lecture_01.pptx
# (or: py -3.11 backend/ingestion/ppt.py data/raw/ppt/lecture_01.pptx)
```
Output saved to: `data/processed/ppt_text/lecture_01_slides.json`

---

## 👥 Team & Architecture

- **Person 1**: Audio & Video Ingestion (`backend/ingestion/audio.py`)
- **Person 2**: PDF & PPT Slide Ingestion (`backend/ingestion/pdf.py`, `backend/ingestion/ppt.py`)
- **Person 3**: Retrieval, Claim Extraction & Evaluation (`backend/retrieval/`, `backend/verification/`)
