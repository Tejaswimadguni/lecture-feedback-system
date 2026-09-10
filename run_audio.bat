@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: run_audio.bat  — Transcribe an audio/video file using Whisper (Python 3.11)
::
:: Usage:
::   run_audio.bat <audio_file> [--lecture-id <id>] [--model <tiny|base|small>]
::
:: Examples:
::   run_audio.bat data\raw\audio\lecture_01.mp3 --lecture-id lecture_01
::   run_audio.bat data\raw\audio\lecture_02.mp4 --lecture-id lecture_02 --model tiny
:: ─────────────────────────────────────────────────────────────────────────────

SET PYTHON311=C:\Users\hpkud\AppData\Local\Python\pythoncore-3.11-64\python.exe

IF NOT EXIST "%PYTHON311%" (
    echo [ERROR] Python 3.11 not found at: %PYTHON311%
    echo Please install Python 3.11 and run: pip install -r requirements.txt
    exit /b 1
)

IF "%1"=="" (
    echo Usage: run_audio.bat ^<audio_file^> [--lecture-id ^<id^>] [--model ^<tiny^|base^|small^>]
    exit /b 1
)

"%PYTHON311%" backend\ingestion\audio.py %*
