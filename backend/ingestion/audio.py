import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.paths import (
    compute_file_sha256,
    get_lecture_paths,
    validate_audio_file,
    validate_identifier,
)

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


def get_audio_duration(audio_path: str) -> float:
    """
    Gets total duration of an audio/video file in seconds using ffmpeg.
    Supports both HH:MM:SS.ms and HH:MM:SS duration formats.
    """
    ffmpeg_exe = _get_ffmpeg_exe()
    cmd = [ffmpeg_exe, "-i", str(audio_path)]
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    _, stderr = process.communicate()

    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if match:
        hours, minutes, seconds = match.groups()
        return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    return 0.0


def transcribe_audio(
    audio_path: str,
    lecture_id: str,
    course_id: Optional[str] = None,
    model_size: str = "base",
    device: Optional[str] = None,
    chunk_length_sec: int = 180,
) -> Dict[str, Any]:
    """
    Production audio ingestion module using OpenAI Whisper.
    Transcribes audio/video files and returns structured timestamped segments.

    Args:
        audio_path: Path to the input audio or video file (e.g. .mp4, .mp3, .wav).
        lecture_id: Explicit identifier for the lecture (required).
        course_id: Optional course identifier to record in raw transcript metadata.
        model_size: OpenAI Whisper model size ('tiny', 'base', 'small', 'medium', 'large').
        device: Torch device ('cpu', 'cuda', etc.). If None, automatically selected by Whisper.
        chunk_length_sec: Length of audio chunks in seconds for long audio files (default: 180s / 3 minutes).

    Returns:
        Dict containing explicit identifiers, source metadata, and timestamped segment objects.
    """
    valid_audio = validate_audio_file(audio_path)
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")
    valid_course_id = validate_identifier(course_id, "course_id") if course_id is not None else None

    try:
        import whisper
    except ImportError as e:
        raise ImportError(
            "openai-whisper package is required. Install it using: pip install -U openai-whisper torch"
        ) from e

    duration = get_audio_duration(str(valid_audio))
    logger.info(f"Ingesting audio file: {valid_audio} (Detected Duration: {duration:.1f}s)")
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
                logger.info(
                    f"  --> Transcribing chunk {chunk_index + 1} ({current_start:.0f}s - {end_sec:.0f}s)..."
                )

                # Extract 16kHz mono WAV chunk using ffmpeg
                cmd = [
                    _get_ffmpeg_exe(),
                    "-y",
                    "-ss",
                    str(current_start),
                    "-t",
                    str(chunk_length_sec),
                    "-i",
                    str(valid_audio),
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    chunk_file,
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
                            "text": text,
                        })

                current_start += chunk_length_sec
                chunk_index += 1

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    else:
        result = model.transcribe(str(valid_audio))
        raw_segments = result.get("segments", [])
        for seg in raw_segments:
            text = str(seg.get("text", "")).strip()
            if text:
                all_segments.append({
                    "start": round(float(seg.get("start", 0.0)), 2),
                    "end": round(float(seg.get("end", 0.0)), 2),
                    "text": text,
                })

    logger.info(f"Transcription complete: Extracted {len(all_segments)} timestamped segments.")
    payload: Dict[str, Any] = {
        "lecture_id": valid_lecture_id,
        "source_file": valid_audio.name,
        "source_sha256": compute_file_sha256(valid_audio),
        "whisper_model": model_size,
        "segments": all_segments,
    }
    if valid_course_id is not None:
        payload["course_id"] = valid_course_id
    return payload


def save_transcript_json(
    audio_path: str,
    course_id: str,
    lecture_id: str,
    output_path: Optional[str] = None,
    model_size: str = "base",
    device: Optional[str] = None,
    data_root: Optional[str] = None,
) -> str:
    """
    Transcribes audio/video file and saves timestamped segments to the lecture's isolated processed path
    (or an explicitly supplied output_path).
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")

    data = transcribe_audio(
        audio_path=audio_path,
        lecture_id=valid_lecture_id,
        course_id=valid_course_id,
        model_size=model_size,
        device=device,
    )

    if output_path:
        dest = Path(output_path).resolve()
    else:
        lpaths = get_lecture_paths(valid_course_id, valid_lecture_id, data_root=data_root)
        dest = lpaths.transcript_raw

    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return str(dest)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest lecture audio/video into timestamped JSON transcript using OpenAI Whisper."
    )
    parser.add_argument("--audio", required=True, help="Path to input audio/video file (.mp3, .mp4, .wav, etc.).")
    parser.add_argument("--course-id", required=True, help="Explicit course identifier.")
    parser.add_argument("--lecture-id", required=True, help="Explicit lecture identifier.")
    parser.add_argument("--output", "-o", default=None, help="Optional explicit output JSON path.")
    parser.add_argument(
        "--model",
        "-m",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: base).",
    )
    parser.add_argument("--device", default=None, help="PyTorch device ('cpu', 'cuda').")
    parser.add_argument("--data-root", default=None, help="Optional custom data root directory.")

    args = parser.parse_args()

    try:
        saved_path = save_transcript_json(
            audio_path=args.audio,
            course_id=args.course_id,
            lecture_id=args.lecture_id,
            output_path=args.output,
            model_size=args.model,
            device=args.device,
            data_root=args.data_root,
        )
        logger.info(f"Successfully transcribed audio into JSON: {saved_path}")
    except Exception as e:
        logger.error(f"Error processing audio: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
