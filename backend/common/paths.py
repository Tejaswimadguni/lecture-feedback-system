import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = PROJECT_ROOT / "backend" / "data"

SUPPORTED_AUDIO_EXTENSIONS = {
    ".mp3",
    ".mp4",
    ".wav",
    ".m4a",
    ".flac",
    ".ogg",
    ".mkv",
    ".webm",
}
SUPPORTED_PDF_EXTENSIONS = {".pdf"}

_FORBIDDEN_ID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_ALNUM_CHECK = re.compile(r"[A-Za-z0-9]")


def validate_identifier(value: Optional[str], field_name: str) -> str:
    """
    Validates course_id or lecture_id to ensure it is explicitly provided,
    non-empty, and safe for filesystem directory construction without path traversal.
    """
    if value is None or not isinstance(value, str):
        raise ValueError(f"{field_name} is required and must be a non-empty string.")

    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty or whitespace.")

    if cleaned in {".", ".."} or ".." in cleaned:
        raise ValueError(f"Invalid {field_name} '{value}': path traversal sequences are not allowed.")

    if _FORBIDDEN_ID_CHARS.search(cleaned):
        raise ValueError(
            f"Invalid {field_name} '{value}': contains forbidden path or control characters."
        )

    if cleaned.endswith("."):
        raise ValueError(f"Invalid {field_name} '{value}': cannot end with a period.")

    if not _ALNUM_CHECK.search(cleaned):
        raise ValueError(
            f"Invalid {field_name} '{value}': must contain at least one alphanumeric character."
        )

    return cleaned


def validate_non_empty_text(value: Optional[str], field_name: str) -> str:
    """Validates that a human-readable string field (such as course_name or lecture_title) is non-empty."""
    if value is None or not isinstance(value, str):
        raise ValueError(f"{field_name} is required and must be a non-empty string.")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty or whitespace.")
    return cleaned


def sanitize_student_id(raw_id: Any) -> str:
    """
    Validates and sanitizes a student identifier from CSV into a safe, unique directory name.
    """
    if raw_id is None:
        raise ValueError("Student identifier cannot be None.")

    raw_str = str(raw_id).strip()
    if not raw_str:
        raise ValueError("Student identifier cannot be empty or whitespace.")

    if raw_str in {".", ".."}:
        raise ValueError(f"Invalid student identifier '{raw_id}'.")

    if not _ALNUM_CHECK.search(raw_str):
        raise ValueError(
            f"Invalid student identifier '{raw_id}': must contain at least one alphanumeric character."
        )

    # Replace any character outside [A-Za-z0-9._-] with underscore
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", raw_str)
    sanitized = sanitized.strip("._") or re.sub(r"[^A-Za-z0-9]", "", raw_str)

    if not sanitized or sanitized in {".", ".."} or ".." in sanitized:
        raise ValueError(f"Invalid student identifier '{raw_id}' after sanitization.")

    return sanitized


def get_data_root(data_root: Optional[Union[str, Path]] = None) -> Path:
    """Resolves the base data root directory (defaults to backend/data)."""
    if data_root is not None:
        return Path(data_root).resolve()
    env_override = os.environ.get("LECTURE_FEEDBACK_DATA_ROOT")
    if env_override:
        return Path(env_override).resolve()
    return DEFAULT_DATA_ROOT.resolve()


@dataclass(frozen=True)
class LecturePaths:
    course_id: str
    lecture_id: str
    data_root: Path
    lecture_dir: Path
    raw_dir: Path
    processed_dir: Path
    metadata_dir: Path
    knowledge_base_dir: Path
    transcript_raw: Path
    transcript_clean: Path
    transcript_chunks: Path
    pdf_raw: Path
    pdf_clean: Path
    pdf_chunks: Path
    dataset_metadata: Path
    faiss_index: Path
    embeddings: Path
    chunk_mapping: Path

    def ensure_dirs(self) -> None:
        """Creates all required lecture subdirectories."""
        for directory in (
            self.raw_dir,
            self.processed_dir,
            self.metadata_dir,
            self.knowledge_base_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


def get_lecture_paths(
    course_id: str,
    lecture_id: str,
    data_root: Optional[Union[str, Path]] = None,
) -> LecturePaths:
    """
    Constructs strict lecture-isolated directory and file paths under:
        {data_root}/lectures/{course_id}/{lecture_id}/
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")
    root = get_data_root(data_root)

    lecture_dir = root / "lectures" / valid_course_id / valid_lecture_id
    raw_dir = lecture_dir / "raw"
    processed_dir = lecture_dir / "processed"
    metadata_dir = lecture_dir / "metadata"
    kb_dir = lecture_dir / "knowledge_base"

    return LecturePaths(
        course_id=valid_course_id,
        lecture_id=valid_lecture_id,
        data_root=root,
        lecture_dir=lecture_dir,
        raw_dir=raw_dir,
        processed_dir=processed_dir,
        metadata_dir=metadata_dir,
        knowledge_base_dir=kb_dir,
        transcript_raw=processed_dir / "transcript_raw.json",
        transcript_clean=processed_dir / "transcript_clean.json",
        transcript_chunks=processed_dir / "transcript_chunks.json",
        pdf_raw=processed_dir / "pdf_raw.json",
        pdf_clean=processed_dir / "pdf_clean.json",
        pdf_chunks=processed_dir / "pdf_chunks.json",
        dataset_metadata=metadata_dir / "dataset_metadata.json",
        faiss_index=kb_dir / "index.faiss",
        embeddings=kb_dir / "embeddings.npy",
        chunk_mapping=kb_dir / "chunk_mapping.json",
    )


def get_results_dir(
    course_id: str,
    lecture_id: str,
    data_root: Optional[Union[str, Path]] = None,
    output_dir: Optional[Union[str, Path]] = None,
) -> Path:
    """
    Resolves the lecture-isolated verification results directory:
        {data_root}/results/{course_id}/{lecture_id}/
    unless an explicit custom output_dir is supplied.
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")
    if output_dir is not None:
        if not str(output_dir).strip():
            raise ValueError("output_dir cannot be empty when specified.")
        return Path(output_dir).resolve()
    root = get_data_root(data_root)
    return root / "results" / valid_course_id / valid_lecture_id


@dataclass(frozen=True)
class StudentResultPaths:
    student_id: str
    sanitized_id: str
    student_dir: Path
    claims: Path
    evidence: Path
    evaluated: Path
    score: Path

    def ensure_dir(self) -> None:
        self.student_dir.mkdir(parents=True, exist_ok=True)


def get_student_result_paths(results_dir: Union[str, Path], raw_student_id: Any) -> StudentResultPaths:
    """Constructs per-student output paths inside the lecture's results directory."""
    safe_id = sanitize_student_id(raw_student_id)
    base = Path(results_dir).resolve() / safe_id
    return StudentResultPaths(
        student_id=str(raw_student_id).strip(),
        sanitized_id=safe_id,
        student_dir=base,
        claims=base / "claims.json",
        evidence=base / "evidence.json",
        evaluated=base / "evaluated.json",
        score=base / "score.json",
    )


def _validate_existing_regular_file(path_value: Optional[Union[str, Path]], label: str) -> Path:
    if path_value is None or not str(path_value).strip():
        raise ValueError(f"{label} path is required and cannot be empty.")
    p = Path(path_value).resolve()
    if not p.exists():
        raise FileNotFoundError(f"{label} file not found at: {p}")
    if not p.is_file():
        raise ValueError(f"{label} path is not a regular file: {p}")
    if p.stat().st_size == 0:
        raise ValueError(f"{label} file is empty (0 bytes): {p}")
    return p


def validate_audio_file(audio_path: Optional[Union[str, Path]]) -> Path:
    """Validates that the supplied audio/video file exists, is non-empty, and has a supported format."""
    p = _validate_existing_regular_file(audio_path, "Audio/video")
    ext = p.suffix.lower()
    if ext not in SUPPORTED_AUDIO_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_AUDIO_EXTENSIONS))
        raise ValueError(
            f"Unsupported audio/video file format '{ext}' for '{p.name}'. Supported formats: {supported}"
        )
    return p


def validate_pdf_file(pdf_path: Optional[Union[str, Path]]) -> Path:
    """Validates that the supplied PDF file exists, is non-empty, and has a .pdf extension."""
    p = _validate_existing_regular_file(pdf_path, "PDF")
    ext = p.suffix.lower()
    if ext not in SUPPORTED_PDF_EXTENSIONS:
        raise ValueError(
            f"Unsupported PDF file format '{ext}' for '{p.name}'. Expected '.pdf'."
        )
    return p


def validate_csv_file(csv_path: Optional[Union[str, Path]]) -> Path:
    """Validates that the supplied student feedback CSV file exists, is non-empty, and has a .csv extension."""
    p = _validate_existing_regular_file(csv_path, "Feedback CSV")
    if p.suffix.lower() != ".csv":
        raise ValueError(
            f"Unsupported feedback file format '{p.suffix}' for '{p.name}'. Expected '.csv'."
        )
    return p


def compute_file_sha256(file_path: Union[str, Path]) -> str:
    """Computes the SHA-256 hex digest of a file for reliable cache validation."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            hasher.update(block)
    return hasher.hexdigest()
