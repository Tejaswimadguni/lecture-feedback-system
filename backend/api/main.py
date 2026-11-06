import sys
from pathlib import Path
from typing import Any, Dict, Optional, Union

from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.jobs import BackgroundJobManager
from backend.api.schemas import (
    ChapterCreateRequest,
    ChapterUpdateRequest,
    EvaluateFeedbackRequest,
    FeedbackMappingConfirmRequest,
    ProcessLectureRequest,
    SubjectCreateRequest,
    SubjectUpdateRequest,
    TeacherCreateRequest,
)
from backend.api.storage import LocalWorkspaceStorage, utc_now_iso
from backend.common.paths import SUPPORTED_AUDIO_EXTENSIONS, SUPPORTED_DOCUMENT_EXTENSIONS


def create_app(data_root: Optional[Union[str, Path]] = None) -> FastAPI:
    storage = LocalWorkspaceStorage(data_root=data_root)
    job_manager = BackgroundJobManager(storage=storage)

    application = FastAPI(
        title="Lecture Feedback & Verification System API",
        version="2.0.0",
        description=(
            "Strict lecture-isolated Whisper + SentenceTransformer + FAISS ingestion, "
            "claim verification, and 10-mark rubric scoring API backed purely by local filesystem storage."
        ),
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.state.storage = storage
    application.state.job_manager = job_manager

    def _handle_domain_error(exc: Exception) -> HTTPException:
        if isinstance(exc, HTTPException):
            return exc
        if isinstance(exc, KeyError):
            msg = exc.args[0] if exc.args else str(exc)
            return HTTPException(status_code=404, detail=str(msg))
        if isinstance(exc, FileNotFoundError):
            return HTTPException(status_code=404, detail=str(exc))
        if isinstance(exc, RuntimeError):
            return HTTPException(status_code=409, detail=str(exc))
        if isinstance(exc, ValueError):
            return HTTPException(status_code=400, detail=str(exc))
        return HTTPException(status_code=500, detail=f"Internal server error: {exc}")

    # =========================================================================
    # SYSTEM & SYNCHRONIZATION
    # =========================================================================

    @application.get("/api/health")
    def health_check() -> Dict[str, Any]:
        return {
            "status": "ok",
            "timestamp": utc_now_iso(),
            "storage_mode": "local_filesystem_no_database",
            "data_root": str(storage.data_root),
            "supported_audio_formats": sorted(SUPPORTED_AUDIO_EXTENSIONS),
            "supported_document_formats": sorted(SUPPORTED_DOCUMENT_EXTENSIONS),
        }

    @application.get("/api/sync")
    def sync_workspace(teacher_id: Optional[str] = Query(default=None)) -> Dict[str, Any]:
        try:
            teachers = storage.list_teachers()
            subjects = storage.list_subjects(teacher_id=teacher_id)
            # Enrich active chapters with live in-memory job progress if any job is running
            for subj in subjects:
                sid = subj["subject_id"]
                for ch in subj.get("chapters", []):
                    lid = ch["lecture_id"]
                    ch["processing"] = job_manager.get_job_status("process", sid, lid)
                    ch["evaluation"] = job_manager.get_job_status("evaluate", sid, lid)
            return {
                "synced_at": utc_now_iso(),
                "data_root": str(storage.data_root),
                "teachers": teachers,
                "subjects": subjects,
            }
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    # =========================================================================
    # TEACHERS
    # =========================================================================

    @application.get("/api/teachers")
    def list_teachers() -> Dict[str, Any]:
        try:
            return {"teachers": storage.list_teachers()}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.post("/api/teachers", status_code=201)
    def create_teacher(payload: TeacherCreateRequest) -> Dict[str, Any]:
        try:
            teacher = storage.create_teacher(name=payload.name, department=payload.department)
            return {"teacher": teacher}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    # =========================================================================
    # SUBJECTS
    # =========================================================================

    @application.get("/api/subjects")
    def list_subjects(teacher_id: Optional[str] = Query(default=None)) -> Dict[str, Any]:
        try:
            subjects = storage.list_subjects(teacher_id=teacher_id)
            for subj in subjects:
                sid = subj["subject_id"]
                for ch in subj.get("chapters", []):
                    lid = ch["lecture_id"]
                    ch["processing"] = job_manager.get_job_status("process", sid, lid)
                    ch["evaluation"] = job_manager.get_job_status("evaluate", sid, lid)
            return {"subjects": subjects}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.post("/api/subjects", status_code=201)
    def create_subject(payload: SubjectCreateRequest) -> Dict[str, Any]:
        try:
            subj = storage.create_subject(
                name=payload.name,
                teacher_id=payload.teacher_id,
                code=payload.code,
            )
            return {"subject": subj}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.get("/api/subjects/{subject_id}")
    def get_subject(subject_id: str) -> Dict[str, Any]:
        try:
            subj = storage.get_subject(subject_id)
            for ch in subj.get("chapters", []):
                lid = ch["lecture_id"]
                ch["processing"] = job_manager.get_job_status("process", subject_id, lid)
                ch["evaluation"] = job_manager.get_job_status("evaluate", subject_id, lid)
            return {"subject": subj}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.patch("/api/subjects/{subject_id}")
    def rename_subject(subject_id: str, payload: SubjectUpdateRequest) -> Dict[str, Any]:
        try:
            subj = storage.rename_subject(subject_id, payload.name)
            return {"subject": subj}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.delete("/api/subjects/{subject_id}")
    def delete_subject(
        subject_id: str,
        confirm: bool = Query(default=False, description="Explicit deletion confirmation required"),
    ) -> Dict[str, Any]:
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail="Subject deletion requires explicit confirmation (?confirm=true).",
            )
        if job_manager.is_subject_busy(subject_id):
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete subject '{subject_id}' while a background job is running.",
            )
        try:
            return storage.delete_subject(subject_id)
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    # =========================================================================
    # CHAPTERS / LECTURES
    # =========================================================================

    @application.get("/api/subjects/{subject_id}/chapters")
    def list_chapters(subject_id: str) -> Dict[str, Any]:
        try:
            chapters = storage.list_chapters(subject_id)
            for ch in chapters:
                lid = ch["lecture_id"]
                ch["processing"] = job_manager.get_job_status("process", subject_id, lid)
                ch["evaluation"] = job_manager.get_job_status("evaluate", subject_id, lid)
            return {"subject_id": subject_id, "chapters": chapters}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.post("/api/subjects/{subject_id}/chapters", status_code=201)
    def create_chapter(subject_id: str, payload: ChapterCreateRequest) -> Dict[str, Any]:
        try:
            chapter = storage.create_chapter(subject_id=subject_id, title=payload.title)
            return {"chapter": chapter}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.get("/api/subjects/{subject_id}/chapters/{lecture_id}")
    def get_chapter(subject_id: str, lecture_id: str) -> Dict[str, Any]:
        try:
            ch = storage.get_chapter(subject_id, lecture_id)
            ch["processing"] = job_manager.get_job_status("process", subject_id, lecture_id)
            ch["evaluation"] = job_manager.get_job_status("evaluate", subject_id, lecture_id)
            return {"chapter": ch}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.patch("/api/subjects/{subject_id}/chapters/{lecture_id}")
    def rename_chapter(
        subject_id: str,
        lecture_id: str,
        payload: ChapterUpdateRequest,
    ) -> Dict[str, Any]:
        try:
            ch = storage.rename_chapter(subject_id, lecture_id, payload.title)
            return {"chapter": ch}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.delete("/api/subjects/{subject_id}/chapters/{lecture_id}")
    def delete_chapter(
        subject_id: str,
        lecture_id: str,
        confirm: bool = Query(default=False, description="Explicit deletion confirmation required"),
    ) -> Dict[str, Any]:
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail="Chapter deletion requires explicit confirmation (?confirm=true).",
            )
        if job_manager.is_lecture_busy(subject_id, lecture_id):
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete chapter '{lecture_id}' while processing or evaluation is active.",
            )
        try:
            return storage.delete_chapter(subject_id, lecture_id)
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    # =========================================================================
    # LECTURE MEDIA UPLOADS (AUDIO & PDF/PPTX)
    # =========================================================================

    @application.post("/api/subjects/{subject_id}/chapters/{lecture_id}/upload/audio")
    async def upload_lecture_audio(
        subject_id: str,
        lecture_id: str,
        file: UploadFile = File(...),
    ) -> Dict[str, Any]:
        if job_manager.is_lecture_busy(subject_id, lecture_id):
            raise HTTPException(status_code=409, detail="Cannot replace audio while a job is running.")
        try:
            data = await file.read()
            ch = storage.save_lecture_media_file(
                subject_id=subject_id,
                lecture_id=lecture_id,
                kind="audio",
                original_filename=file.filename or "audio.mp3",
                content_bytes=data,
            )
            return {"chapter": ch}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.post("/api/subjects/{subject_id}/chapters/{lecture_id}/upload/document")
    async def upload_lecture_document(
        subject_id: str,
        lecture_id: str,
        file: UploadFile = File(...),
    ) -> Dict[str, Any]:
        if job_manager.is_lecture_busy(subject_id, lecture_id):
            raise HTTPException(status_code=409, detail="Cannot replace slides/PDF while a job is running.")
        try:
            data = await file.read()
            ch = storage.save_lecture_media_file(
                subject_id=subject_id,
                lecture_id=lecture_id,
                kind="document",
                original_filename=file.filename or "slides.pdf",
                content_bytes=data,
            )
            return {"chapter": ch}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.delete("/api/subjects/{subject_id}/chapters/{lecture_id}/files/{file_kind}")
    def remove_lecture_file(
        subject_id: str,
        lecture_id: str,
        file_kind: str,
    ) -> Dict[str, Any]:
        if job_manager.is_lecture_busy(subject_id, lecture_id):
            raise HTTPException(status_code=409, detail="Cannot remove files while a job is running.")
        try:
            ch = storage.remove_lecture_file(subject_id, lecture_id, file_kind)
            return {"chapter": ch}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    # =========================================================================
    # LECTURE PROCESSING & KNOWLEDGE BASE INDEXING
    # =========================================================================

    @application.post("/api/subjects/{subject_id}/chapters/{lecture_id}/process", status_code=202)
    def process_lecture(
        subject_id: str,
        lecture_id: str,
        payload: Optional[ProcessLectureRequest] = None,
    ) -> Dict[str, Any]:
        req = payload or ProcessLectureRequest()
        try:
            status = job_manager.start_lecture_processing(
                subject_id=subject_id,
                lecture_id=lecture_id,
                whisper_model=req.whisper_model,
                force_reprocess=req.force_reprocess,
                audio_only=req.audio_only,
                pdf_only=req.pdf_only,
            )
            return {"subject_id": subject_id, "lecture_id": lecture_id, "processing": status}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.get("/api/subjects/{subject_id}/chapters/{lecture_id}/process/status")
    def get_processing_status(subject_id: str, lecture_id: str) -> Dict[str, Any]:
        try:
            status = job_manager.get_job_status("process", subject_id, lecture_id)
            return {"subject_id": subject_id, "lecture_id": lecture_id, "processing": status}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.get("/api/subjects/{subject_id}/chapters/{lecture_id}/metadata")
    def get_lecture_metadata(subject_id: str, lecture_id: str) -> Dict[str, Any]:
        try:
            return storage.get_lecture_metadata(subject_id, lecture_id)
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    # =========================================================================
    # STUDENT FEEDBACK CSV UPLOAD, PREVIEW & COLUMN CONFIRMATION
    # =========================================================================

    @application.post("/api/subjects/{subject_id}/chapters/{lecture_id}/feedback/upload")
    async def upload_feedback_csv(
        subject_id: str,
        lecture_id: str,
        file: UploadFile = File(...),
    ) -> Dict[str, Any]:
        if job_manager.is_lecture_busy(subject_id, lecture_id):
            raise HTTPException(status_code=409, detail="Cannot replace feedback CSV during active evaluation.")
        try:
            data = await file.read()
            return storage.save_feedback_csv(
                subject_id=subject_id,
                lecture_id=lecture_id,
                original_filename=file.filename or "feedback.csv",
                content_bytes=data,
            )
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.get("/api/subjects/{subject_id}/chapters/{lecture_id}/feedback/preview")
    def preview_feedback_csv(
        subject_id: str,
        lecture_id: str,
        student_id_column: Optional[str] = Query(default=None),
        feedback_column: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        try:
            preview = storage.get_feedback_preview(
                subject_id=subject_id,
                lecture_id=lecture_id,
                student_id_column=student_id_column,
                feedback_column=feedback_column,
            )
            return {"preview": preview}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.post("/api/subjects/{subject_id}/chapters/{lecture_id}/feedback/confirm")
    def confirm_feedback_columns(
        subject_id: str,
        lecture_id: str,
        payload: FeedbackMappingConfirmRequest,
    ) -> Dict[str, Any]:
        try:
            return storage.confirm_feedback_mapping(
                subject_id=subject_id,
                lecture_id=lecture_id,
                student_id_column=payload.student_id_column,
                feedback_column=payload.feedback_column,
            )
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    # =========================================================================
    # VERIFICATION & EVALUATION EXECUTION
    # =========================================================================

    @application.post("/api/subjects/{subject_id}/chapters/{lecture_id}/evaluate", status_code=202)
    def evaluate_student_feedback(
        subject_id: str,
        lecture_id: str,
        payload: Optional[EvaluateFeedbackRequest] = None,
    ) -> Dict[str, Any]:
        req = payload or EvaluateFeedbackRequest()
        try:
            status = job_manager.start_feedback_evaluation(
                subject_id=subject_id,
                lecture_id=lecture_id,
                student_id_column=req.student_id_column,
                feedback_column=req.feedback_column,
                top_k=req.top_k,
                overwrite_existing=req.overwrite_existing,
                strict_llm=req.strict_llm,
            )
            return {"subject_id": subject_id, "lecture_id": lecture_id, "evaluation": status}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.get("/api/subjects/{subject_id}/chapters/{lecture_id}/evaluate/status")
    def get_evaluation_status(subject_id: str, lecture_id: str) -> Dict[str, Any]:
        try:
            status = job_manager.get_job_status("evaluate", subject_id, lecture_id)
            return {"subject_id": subject_id, "lecture_id": lecture_id, "evaluation": status}
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    # =========================================================================
    # RESULTS, STUDENT DETAILS & REPORT EXPORT
    # =========================================================================

    @application.get("/api/subjects/{subject_id}/chapters/{lecture_id}/results")
    def get_lecture_results(subject_id: str, lecture_id: str) -> Dict[str, Any]:
        try:
            return storage.get_lecture_results(subject_id, lecture_id)
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.get("/api/subjects/{subject_id}/chapters/{lecture_id}/results/export")
    def export_results_report(
        subject_id: str,
        lecture_id: str,
        format: str = Query(default="csv", description="Export format: csv or json"),
        student_id: Optional[str] = Query(default=None, description="Optional single student ID"),
    ) -> Response:
        try:
            body, media_type, filename = storage.export_results_report(
                subject_id=subject_id,
                lecture_id=lecture_id,
                fmt=format,
                student_id=student_id,
            )
            return Response(
                content=body,
                media_type=media_type,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.get("/api/subjects/{subject_id}/chapters/{lecture_id}/results/{student_id:path}")
    def get_student_result(subject_id: str, lecture_id: str, student_id: str) -> Dict[str, Any]:
        try:
            return storage.get_student_result_detail(subject_id, lecture_id, student_id)
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    # =========================================================================
    # LOCAL BACKUP EXPORT & RESTORE
    # =========================================================================

    @application.get("/api/backup/export")
    def export_workspace_backup(
        include_knowledge_base: bool = Query(
            default=False,
            description="Include FAISS indexes and processed JSONs in backup archive",
        ),
    ) -> Response:
        try:
            zip_bytes = storage.export_backup_zip(include_knowledge_base=include_knowledge_base)
            stamp = utc_now_iso()[:10]
            fname = f"lecture_feedback_backup_{stamp}.zip"
            return Response(
                content=zip_bytes,
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="{fname}"'},
            )
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    @application.post("/api/backup/restore")
    async def restore_workspace_backup(file: UploadFile = File(...)) -> Dict[str, Any]:
        try:
            zip_bytes = await file.read()
            return storage.restore_backup_zip(zip_bytes)
        except Exception as exc:
            raise _handle_domain_error(exc) from exc

    return application


app = create_app()

