@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: run_audio.bat  — Transcribe an audio/video file using Whisper
::
:: Usage:
::   run_audio.bat --audio <audio_file> --course-id <course_id> --lecture-id <lecture_id> [--model <tiny|base|small>]
::
:: Example:
::   run_audio.bat --audio data\raw\audio\normalization.mp3 --course-id DBMS --lecture-id DBMS_lect1
:: ─────────────────────────────────────────────────────────────────────────────

python backend\ingestion\audio.py %*
