from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TeacherCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Teacher display name")
    department: Optional[str] = Field(default="Computer Science & Engineering", description="Department or faculty")


class SubjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Subject display name (e.g., Database Management Systems)")
    code: Optional[str] = Field(default=None, description="Optional short subject code/ID hint (e.g., DBMS)")
    teacher_id: str = Field(..., min_length=1, description="Selected teacher profile ID")


class SubjectUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Updated subject display name")


class ChapterCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, description="Chapter / lecture title (e.g., Normalization)")


class ChapterUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, description="Updated chapter / lecture title")


class ProcessLectureRequest(BaseModel):
    whisper_model: str = Field(default="base", description="Whisper model size: tiny, base, small, medium, large")
    force_reprocess: bool = Field(default=False, description="Force full reprocessing even when SHA-256 cache matches")
    audio_only: bool = Field(default=False, description="Explicitly process audio only without slides/PDF")
    pdf_only: bool = Field(default=False, description="Explicitly process slides/PDF only without audio")


class FeedbackMappingConfirmRequest(BaseModel):
    student_id_column: str = Field(..., min_length=1, description="CSV column containing unique student IDs")
    feedback_column: str = Field(..., min_length=1, description="CSV column containing student feedback text")


class EvaluateFeedbackRequest(BaseModel):
    student_id_column: Optional[str] = Field(default=None, description="CSV column for student IDs")
    feedback_column: Optional[str] = Field(default=None, description="CSV column for feedback text")
    top_k: int = Field(default=5, ge=1, le=20, description="Top-K lecture chunks retrieved per claim")
    overwrite_existing: bool = Field(
        default=True,
        description="Whether to replace existing evaluation results for this lecture",
    )
    strict_llm: bool = Field(
        default=False,
        description="Fail immediately instead of using deterministic fallback when LLM API is unavailable",
    )

