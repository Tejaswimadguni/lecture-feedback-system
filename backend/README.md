# Backend — FastAPI Server & Lecture-Isolated Verification Engine

Python backend powering Whisper transcription, PDF/PPTX slide ingestion, lecture-isolated SentenceTransformer + FAISS indexing, LLM/deterministic student claim verification, and 10-mark rubric scoring with **zero external database dependencies**.

## Starting the API Server

```powershell
# From lecture-feedback-system/
python backend/main.py
# Or:
uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Interactive OpenAPI documentation is served at `http://127.0.0.1:8000/docs`.

## Key REST API Endpoints

- **System & Sync**: `GET /api/health`, `GET /api/sync`
- **Teachers**: `GET /api/teachers`, `POST /api/teachers`
- **Subjects**: `GET /api/subjects`, `POST /api/subjects`, `GET /api/subjects/{subject_id}`, `PATCH /api/subjects/{subject_id}`, `DELETE /api/subjects/{subject_id}?confirm=true`
- **Chapters / Lectures**: `GET /api/subjects/{subject_id}/chapters`, `POST /api/subjects/{subject_id}/chapters`, `GET /api/subjects/{subject_id}/chapters/{lecture_id}`, `PATCH /api/subjects/{subject_id}/chapters/{lecture_id}`, `DELETE /api/subjects/{subject_id}/chapters/{lecture_id}?confirm=true`
- **Lecture Media Uploads**:
  - `POST /api/subjects/{subject_id}/chapters/{lecture_id}/upload/audio`
  - `POST /api/subjects/{subject_id}/chapters/{lecture_id}/upload/document` (`.pdf` or `.pptx`)
  - `DELETE /api/subjects/{subject_id}/chapters/{lecture_id}/files/{file_kind}`
- **Processing & KB Metadata**:
  - `POST /api/subjects/{subject_id}/chapters/{lecture_id}/process`
  - `GET /api/subjects/{subject_id}/chapters/{lecture_id}/process/status`
  - `GET /api/subjects/{subject_id}/chapters/{lecture_id}/metadata`
- **Feedback CSV Upload & Validation**:
  - `POST /api/subjects/{subject_id}/chapters/{lecture_id}/feedback/upload`
  - `GET /api/subjects/{subject_id}/chapters/{lecture_id}/feedback/preview`
  - `POST /api/subjects/{subject_id}/chapters/{lecture_id}/feedback/confirm`
- **Verification & Results**:
  - `POST /api/subjects/{subject_id}/chapters/{lecture_id}/evaluate`
  - `GET /api/subjects/{subject_id}/chapters/{lecture_id}/evaluate/status`
  - `GET /api/subjects/{subject_id}/chapters/{lecture_id}/results`
  - `GET /api/subjects/{subject_id}/chapters/{lecture_id}/results/{student_id}`
  - `GET /api/subjects/{subject_id}/chapters/{lecture_id}/results/export?format=csv|json`
- **Local Backup**: `GET /api/backup/export`, `POST /api/backup/restore`
