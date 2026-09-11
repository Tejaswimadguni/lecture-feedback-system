import os
import json
import argparse
import re
import shutil
import tempfile
import subprocess
import logging
from typing import Dict, Any, Optional

# Configure production logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def _get_ffmpeg_exe() -> str:
    """
    Resolves the ffmpeg executable path.
    Uses imageio-ffmpeg static binary if available (no system install needed).
    Falls back to system 'ffmpeg' if imageio_ffmpeg is not installed.
    """
    try:
        # pyrefly: ignore [missing-import]
        import imageio_ffmpeg
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        # Create ffmpeg.exe alias in the same directory for subprocess compatibility
        ffmpeg_dir = os.path.dirname(ffmpeg_bin)
        alias = os.path.join(ffmpeg_dir, "ffmpeg.exe")
        if not os.path.exists(alias) and os.path.exists(ffmpeg_bin):
            shutil.copyfile(ffmpeg_bin, alias)
        return alias if os.path.exists(alias) else ffmpeg_bin
    except Exception:
        return "ffmpeg"  # Fall back to system ffmpeg on PATH


# Inject ffmpeg directory into PATH at module load time.
# This ensures Whisper's own internal load_audio() subprocess call also finds ffmpeg.
try:
    _ffmpeg_resolved = _get_ffmpeg_exe()
    _ffmpeg_dir = os.path.dirname(_ffmpeg_resolved)
    if _ffmpeg_dir and _ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass


def derive_lecture_id(file_path: str) -> str:
    """Derives a lecture ID from a filename by stripping path and extension."""
    basename = os.path.basename(file_path)
    lecture_id, _ = os.path.splitext(basename)
    return lecture_id


def get_audio_duration(audio_path: str) -> float:
    """
    Gets total duration of an audio/video file in seconds using ffmpeg.
    Supports both HH:MM:SS.ms and HH:MM:SS duration formats.
    """
    ffmpeg_exe = _get_ffmpeg_exe()
    cmd = [ffmpeg_exe, "-i", audio_path]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    _, stderr = process.communicate()
    
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if match:
        hours, minutes, seconds = match.groups()
        return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    return 0.0


def transcribe_audio(
    audio_path: str,
    model_size: str = "base",
    lecture_id: Optional[str] = None,
    device: Optional[str] = None,
    chunk_length_sec: int = 180
) -> Dict[str, Any]:
    """
    Production audio ingestion module using OpenAI Whisper.
    Transcribes audio/video files and returns structured timestamped segments.

    Args:
        audio_path: Path to the input audio or video file (e.g. .mp4, .mp3, .wav).
        model_size: OpenAI Whisper model size ('tiny', 'base', 'small', 'medium', 'large').
        lecture_id: Identifier for the lecture. If None, derived from filename.
        device: Torch device ('cpu', 'cuda', etc.). If None, automatically selected by Whisper.
        chunk_length_sec: Length of audio chunks in seconds for long audio files (default: 180s / 3 minutes).

    Returns:
        Dict containing lecture_id and a list of timestamped segment objects:
        {
          "lecture_id": "lecture_01",
          "segments": [
            {
              "start": 0.0,
              "end": 5.2,
              "text": "Welcome to the course."
            }
          ]
        }
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio/video file not found at: {audio_path}")

    if not lecture_id:
        lecture_id = derive_lecture_id(audio_path)

    try:
        import whisper
    except ImportError as e:
        raise ImportError(
            "openai-whisper package is required. Install it using: pip install -U openai-whisper torch"
        ) from e

    duration = get_audio_duration(audio_path)
    logger.info(f"Ingesting audio file: {audio_path} (Detected Duration: {duration:.1f}s)")
    logger.info(f"Loading Whisper model '{model_size}'...")
    
    model = whisper.load_model(model_size, device=device)
    all_segments = []

    # Process long audio (> 3 minutes) in chunks to avoid PyTorch CPU memory allocation bottlenecks
    if duration > chunk_length_sec:
        temp_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
        try:
            current_start = 0.0
            chunk_index = 0

            while current_start < duration:
                chunk_file = os.path.join(temp_dir, f"chunk_{chunk_index:04d}.wav")
                end_sec = min(current_start + chunk_length_sec, duration)
                logger.info(f"  --> Transcribing chunk {chunk_index + 1} ({current_start:.0f}s - {end_sec:.0f}s)...")
                
                # Extract 16kHz mono WAV chunk using ffmpeg
                cmd = [
                    _get_ffmpeg_exe(), "-y", "-ss", str(current_start), "-t", str(chunk_length_sec),
                    "-i", audio_path, "-ar", "16000", "-ac", "1", chunk_file
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

                result = model.transcribe(chunk_file)
                raw_segments = result.get("segments", [])

                for seg in raw_segments:
                    start_time = round(float(seg.get("start", 0.0)) + current_start, 2)
                    end_time = round(float(seg.get("end", 0.0)) + current_start, 2)
                    text = str(seg.get("text", "")).strip()
                    if text:
                        all_segments.append({
                            "start": start_time,
                            "end": end_time,
                            "text": text
                        })

                current_start += chunk_length_sec
                chunk_index += 1

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    else:
        result = model.transcribe(audio_path)
        raw_segments = result.get("segments", [])
        for seg in raw_segments:
            text = str(seg.get("text", "")).strip()
            if text:
                all_segments.append({
                    "start": round(float(seg.get("start", 0.0)), 2),
                    "end": round(float(seg.get("end", 0.0)), 2),
                    "text": text
                })

    logger.info(f"Transcription complete: Extracted {len(all_segments)} timestamped segments.")
    return {
        "lecture_id": lecture_id,
        "segments": all_segments
    }


def save_transcript_json(
    audio_path: str,
    output_path: Optional[str] = None,
    model_size: str = "base",
    lecture_id: Optional[str] = None
) -> str:
    """
    Transcribes audio/video file and saves timestamped segments to a JSON file.

    Args:
        audio_path: Path to input audio/video file.
        output_path: Path where JSON should be saved. If None, defaults to data/processed/transcripts/<lecture_id>_transcript.json.
        model_size: OpenAI Whisper model size.
        lecture_id: Identifier for the lecture. If None, derived from filename.

    Returns:
        Path to the saved JSON file.
    """
    data = transcribe_audio(audio_path, model_size=model_size, lecture_id=lecture_id)

    if not output_path:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        output_dir = os.path.join(base_dir, "data", "processed", "transcripts")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{data['lecture_id']}_transcript.json")
    else:
        parent_dir = os.path.dirname(os.path.abspath(output_path))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return output_path


def find_all_raw_audio() -> list[str]:
    """Finds all available raw audio or video files in data/raw/audio or data/raw/video."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    search_dirs = [
        os.path.join(base_dir, "data", "raw", "audio"),
        os.path.join(base_dir, "data", "raw", "video"),
    ]
    valid_extensions = {".mp3", ".mp4", ".wav", ".m4a", ".flac", ".ogg", ".mkv"}
    discovered = []

    for search_dir in search_dirs:
        if os.path.exists(search_dir):
            for filename in sorted(os.listdir(search_dir)):
                ext = os.path.splitext(filename)[1].lower()
                if ext in valid_extensions:
                    discovered.append(os.path.join(search_dir, filename))
    return discovered


def find_default_raw_audio() -> Optional[str]:
    """Finds the first available raw audio or video file in data/raw/audio or data/raw/video."""
    all_files = find_all_raw_audio()
    return all_files[0] if all_files else None


def main():
    parser = argparse.ArgumentParser(
        description="Ingest lecture audio/video into timestamped JSON transcript using OpenAI Whisper."
    )
    parser.add_argument(
        "audio_path",
        nargs="?",
        default=None,
        help="Path to input audio/video file (e.g., .mp4, .mp3, .wav). If omitted, scans data/raw/ for files."
    )
    parser.add_argument("--output", "-o", help="Optional path to output JSON file")
    parser.add_argument("--model", "-m", default="base", help="Whisper model size: tiny, base, small, medium (default: base)")
    parser.add_argument("--lecture-id", "-l", help="Optional lecture ID")
    parser.add_argument("--all", "-a", action="store_true", help="Batch process all audio/video files found in data/raw/")

    args = parser.parse_args()

    # Batch process all files if requested
    if args.all:
        files = find_all_raw_audio()
        if not files:
            logger.error("No audio/video files found in data/raw/audio or data/raw/video.")
            return
        logger.info(f"Found {len(files)} files to transcribe: {[os.path.basename(f) for f in files]}")
        for filepath in files:
            try:
                lid = derive_lecture_id(filepath)
                logger.info(f"=== Starting transcription for: {os.path.basename(filepath)} (ID: {lid}) ===")
                saved_path = save_transcript_json(filepath, model_size=args.model, lecture_id=lid)
                logger.info(f"Finished: {saved_path}")
            except Exception as e:
                logger.error(f"Failed to transcribe {filepath}: {e}", exc_info=True)
        return

    audio_path = args.audio_path

    if not audio_path:
        audio_path = find_default_raw_audio()
        if audio_path:
            logger.info(f"No audio_path specified. Automatically using discovered raw file: {audio_path}")
        else:
            logger.error("No audio_path specified and no audio/video files found in data/raw/audio or data/raw/video.")
            print("\nUsage example:")
            print("  python backend/ingestion/audio.py data/raw/audio/lecture_01.mp3")
            print("  python backend/ingestion/audio.py data/raw/video/lecture_02.mp4 --lecture-id lecture_02")
            print("  python backend/ingestion/audio.py --all --model tiny")
            return

    try:
        saved_path = save_transcript_json(
            audio_path,
            output_path=args.output,
            model_size=args.model,
            lecture_id=args.lecture_id
        )
        logger.info(f"Successfully transcribed audio into JSON: {saved_path}")
    except Exception as e:
        logger.error(f"Error processing audio: {e}", exc_info=True)


if __name__ == "__main__":
    main()