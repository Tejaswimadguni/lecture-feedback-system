# Frontend — Teacher Dashboard (React + Vite + IndexedDB)

Interactive 8-stage Teacher Dashboard for the Lecture Feedback & Verification System.

## Features

1. **Teacher Selection**: Switch between faculty profiles or create new profiles (no login/auth required).
2. **Subject Management**: Create, inspect, rename, and delete subjects with confirmation.
3. **Chapter / Lecture Management**: Automatically generates unique lecture IDs (`{subject_id}_lect1`, `{subject_id}_lect2`, ...) — never derived from uploaded filenames.
4. **Lecture File Upload**: Upload arbitrary audio/video (`.mp3`, `.wav`, `.m4a`, `.mp4`, etc.) and slides/notes (`.pdf`, `.pptx`), persisted in both backend local disk and browser **IndexedDB**.
5. **Lecture Processing**: Configure Whisper model & ingestion mode, view real stage and Whisper segment progress, and inspect the isolated FAISS knowledge base.
6. **Student Feedback CSV**: Upload custom CSVs, preview student rows, map Student ID & Feedback columns, and validate against duplicate IDs, collisions, and empty cells.
7. **Evaluation**: Run isolated lecture verification with live per-student progress and re-evaluation safeguards.
8. **Verification Results**: Class leaderboard, rubric averages, grade distribution, detailed per-student claim & lecture evidence inspector (with audio timestamps `MM:SS` and slide page numbers), downloadable CSV/JSON reports, and `.zip` workspace backup/restore.

## Commands

```powershell
# Install dependencies
npm install

# Start development server at http://localhost:5173 (proxies /api to http://127.0.0.1:8000)
npm run dev

# Build production bundle
npm run build
```
