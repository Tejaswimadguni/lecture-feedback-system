import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.api.storage import LocalWorkspaceStorage, utc_now_iso
from backend.common.paths import get_lecture_paths, get_results_dir
from backend.retrival.vector_store import validate_and_load_knowledge_base
from backend.run_lecture_pipeline import run_pipeline
from backend.verification.claims import load_and_validate_feedback_csv
from backend.verification.llm_client import redact_secrets, snapshot_llm_stats
from backend.verification.pipeline import run_verification_pipeline


class BackgroundJobManager:
    """
    Executes long-running Whisper lecture ingestion and student feedback verification
    in background worker threads while persisting real stage progress to disk.
    """

    def __init__(self, storage: LocalWorkspaceStorage, max_workers: int = 2) -> None:
        self.storage = storage
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="lfs_worker")
        self._lock = threading.RLock()
        # Keyed by f"{kind}::{subject_id}::{lecture_id}" where kind in {"process", "evaluate"}
        self._jobs: Dict[str, Dict[str, Any]] = {}
        # Active lecture lock keys f"{subject_id}::{lecture_id}"
        self._active_lectures: set[str] = set()

    @staticmethod
    def _lecture_key(subject_id: str, lecture_id: str) -> str:
        return f"{subject_id}::{lecture_id}"

    @staticmethod
    def _job_key(kind: str, subject_id: str, lecture_id: str) -> str:
        return f"{kind}::{subject_id}::{lecture_id}"

    def is_lecture_busy(self, subject_id: str, lecture_id: str) -> bool:
        with self._lock:
            return self._lecture_key(subject_id, lecture_id) in self._active_lectures

    def is_subject_busy(self, subject_id: str) -> bool:
        prefix = f"{subject_id}::"
        with self._lock:
            return any(k.startswith(prefix) for k in self._active_lectures)

    def get_job_status(self, kind: str, subject_id: str, lecture_id: str) -> Dict[str, Any]:
        ch = self.storage.get_chapter(subject_id, lecture_id)
        persisted = ch.get("processing" if kind == "process" else "evaluation", {})
        jkey = self._job_key(kind, subject_id, lecture_id)

        with self._lock:
            live = dict(self._jobs[jkey]) if jkey in self._jobs else None

        if live is not None:
            if live.get("status") in ("queued", "processing", "evaluating") and live.get("started_monotonic"):
                live["elapsed_seconds"] = round(time.monotonic() - live["started_monotonic"], 1)
            out = dict(persisted)
            for k, v in live.items():
                if k != "started_monotonic":
                    out[k] = v
            return out

        return dict(persisted)

    # =========================================================================
    # LECTURE INGESTION & KB BUILD JOB
    # =========================================================================

    def start_lecture_processing(
        self,
        subject_id: str,
        lecture_id: str,
        whisper_model: str = "base",
        force_reprocess: bool = False,
        audio_only: bool = False,
        pdf_only: bool = False,
    ) -> Dict[str, Any]:
        if whisper_model not in {"tiny", "base", "small", "medium", "large"}:
            raise ValueError(f"Unsupported whisper_model '{whisper_model}'.")
        if audio_only and pdf_only:
            raise ValueError("Cannot enable both audio_only and pdf_only simultaneously.")

        ch = self.storage.get_chapter(subject_id, lecture_id)
        lpaths = get_lecture_paths(subject_id, lecture_id, data_root=self.storage.data_root)

        audio_rec = ch.get("files", {}).get("audio")
        doc_rec = ch.get("files", {}).get("document")

        audio_path: Optional[Path] = (
            lpaths.raw_dir / audio_rec["filename"]
            if isinstance(audio_rec, dict) and audio_rec.get("filename")
            else None
        )
        doc_path: Optional[Path] = (
            lpaths.raw_dir / doc_rec["filename"]
            if isinstance(doc_rec, dict) and doc_rec.get("filename")
            else None
        )

        if audio_only:
            if not audio_path or not audio_path.is_file():
                raise ValueError("Audio file must be uploaded before running in audio-only mode.")
            doc_path = None
        elif pdf_only:
            if not doc_path or not doc_path.is_file():
                raise ValueError("PDF/PPTX file must be uploaded before running in document-only mode.")
            audio_path = None
        else:
            if not audio_path or not audio_path.is_file():
                raise ValueError(
                    "Missing lecture audio file. Upload both lecture audio and PDF/PPTX slides (or select PDF-only mode)."
                )
            if not doc_path or not doc_path.is_file():
                raise ValueError(
                    "Missing lecture PDF/PPTX slides. Upload both lecture audio and PDF/PPTX slides (or select Audio-only mode)."
                )

        lkey = self._lecture_key(subject_id, lecture_id)
        jkey = self._job_key("process", subject_id, lecture_id)

        with self._lock:
            if lkey in self._active_lectures:
                raise RuntimeError(
                    f"A processing or evaluation job is already running for '{subject_id}/{lecture_id}'."
                )
            self._active_lectures.add(lkey)
            job_id = f"proc_{uuid.uuid4().hex[:10]}"
            now = utc_now_iso()
            job_state: Dict[str, Any] = {
                "job_id": job_id,
                "status": "processing",
                "stage": "Initializing lecture ingestion pipeline",
                "stage_index": 0,
                "stage_count": 5,
                "message": "Validating lecture files and preparing directories",
                "current": None,
                "total": None,
                "whisper_model": whisper_model,
                "started_at": now,
                "updated_at": now,
                "started_monotonic": time.monotonic(),
                "elapsed_seconds": 0.0,
                "error": None,
                "outdated_reason": None,
                "can_retry": False,
            }
            self._jobs[jkey] = job_state

        self.storage.update_processing_state(
            subject_id,
            lecture_id,
            {
                "job_id": job_id,
                "status": "processing",
                "stage": job_state["stage"],
                "stage_index": 0,
                "stage_count": 5,
                "whisper_model": whisper_model,
                "error": None,
                "outdated_reason": None,
            },
        )

        def _progress(ev: Dict[str, Any]) -> None:
            with self._lock:
                st = self._jobs.get(jkey)
                if st is not None:
                    st["stage"] = ev.get("stage") or st["stage"]
                    st["stage_index"] = ev.get("stage_index", st["stage_index"])
                    st["stage_count"] = ev.get("stage_count", st["stage_count"])
                    st["message"] = ev.get("message") or st["stage"]
                    st["current"] = ev.get("current")
                    st["total"] = ev.get("total")
                    st["updated_at"] = utc_now_iso()
            self.storage.update_processing_state(
                subject_id,
                lecture_id,
                {
                    "status": "processing",
                    "stage": ev.get("stage"),
                    "stage_index": ev.get("stage_index", 0),
                    "stage_count": ev.get("stage_count", 5),
                },
            )

        def _worker() -> None:
            t0 = time.monotonic()
            try:
                summary = run_pipeline(
                    course_id=subject_id,
                    lecture_id=lecture_id,
                    course_name=ch["subject_name"],
                    lecture_title=ch["title"],
                    audio_path=audio_path,
                    pdf_path=doc_path,
                    audio_only=audio_only,
                    pdf_only=pdf_only,
                    whisper_model=whisper_model,
                    force_reprocess=force_reprocess,
                    data_root=self.storage.data_root,
                    progress_callback=_progress,
                )
                elapsed = round(time.monotonic() - t0, 2)
                done_iso = utc_now_iso()
                persisted_done = {
                    "job_id": job_id,
                    "status": "completed",
                    "stage": "Knowledge base ready",
                    "stage_index": 5,
                    "stage_count": 5,
                    "message": (
                        f"Indexed {summary['total_index_chunks']} chunks "
                        f"({summary['transcript_chunks']} transcript, {summary['pdf_chunks']} slide/PDF)"
                    ),
                    "current": None,
                    "total": None,
                    "whisper_model": whisper_model,
                    "transcript_chunks": summary["transcript_chunks"],
                    "pdf_chunks": summary["pdf_chunks"],
                    "total_chunks": summary["total_index_chunks"],
                    "lecture_concepts_count": summary["lecture_concepts_count"],
                    "last_processed_at": done_iso,
                    "elapsed_seconds": elapsed,
                    "outdated_reason": None,
                    "error": None,
                    "can_retry": False,
                }
                self.storage.update_processing_state(subject_id, lecture_id, persisted_done)

                # If evaluation results already existed prior to reprocessing, mark evaluation as outdated
                latest_ch = self.storage.get_chapter(subject_id, lecture_id)
                if latest_ch.get("evaluation", {}).get("status") == "completed":
                    self.storage.update_evaluation_state(
                        subject_id,
                        lecture_id,
                        {"outdated": True},
                    )

                with self._lock:
                    self._jobs[jkey] = dict(persisted_done)
            except Exception as exc:
                safe_err = redact_secrets(str(exc))
                elapsed = round(time.monotonic() - t0, 2)
                fail_state = {
                    "job_id": job_id,
                    "status": "failed",
                    "stage": "Processing failed",
                    "message": safe_err,
                    "error": safe_err,
                    "elapsed_seconds": elapsed,
                    "can_retry": True,
                }
                self.storage.update_processing_state(subject_id, lecture_id, fail_state)
                with self._lock:
                    if jkey in self._jobs:
                        self._jobs[jkey].update(fail_state)
            finally:
                with self._lock:
                    self._active_lectures.discard(lkey)

        self._executor.submit(_worker)
        return self.get_job_status("process", subject_id, lecture_id)

    # =========================================================================
    # STUDENT FEEDBACK VERIFICATION & EVALUATION JOB
    # =========================================================================

    def start_feedback_evaluation(
        self,
        subject_id: str,
        lecture_id: str,
        student_id_column: Optional[str] = None,
        feedback_column: Optional[str] = None,
        top_k: int = 5,
        overwrite_existing: bool = True,
        strict_llm: bool = False,
    ) -> Dict[str, Any]:
        ch = self.storage.get_chapter(subject_id, lecture_id)

        # 1. Verify lecture knowledge base exists and is consistent BEFORE queuing
        try:
            validate_and_load_knowledge_base(
                course_id=subject_id,
                lecture_id=lecture_id,
                data_root=self.storage.data_root,
            )
        except FileNotFoundError as exc:
            raise ValueError(
                f"Lecture '{subject_id}/{lecture_id}' has not been processed yet. "
                f"Process the lecture knowledge base before evaluating student feedback. ({exc})"
            ) from exc

        # 2. Verify feedback CSV & columns upfront so invalid CSVs fail synchronously with HTTP 400
        csv_rec = ch.get("files", {}).get("feedback_csv")
        if not isinstance(csv_rec, dict) or not csv_rec.get("filename"):
            raise ValueError("No student feedback CSV has been uploaded for this lecture.")

        lpaths = get_lecture_paths(subject_id, lecture_id, data_root=self.storage.data_root)
        csv_path = lpaths.inputs_dir / csv_rec["filename"]
        id_col = student_id_column or csv_rec.get("student_id_column") or "roll_number"
        fb_col = feedback_column or csv_rec.get("feedback_column") or "feedback"

        student_entries = load_and_validate_feedback_csv(
            csv_path=csv_path,
            student_id_column=id_col,
            feedback_column=fb_col,
        )

        res_dir = get_results_dir(subject_id, lecture_id, data_root=self.storage.data_root)
        if (res_dir / "all_students_summary.json").is_file() and not overwrite_existing:
            raise ValueError(
                "Evaluation results already exist for this lecture. Confirm re-evaluation to replace them."
            )

        # Persist confirmed mapping
        self.storage.confirm_feedback_mapping(subject_id, lecture_id, id_col, fb_col)

        lkey = self._lecture_key(subject_id, lecture_id)
        jkey = self._job_key("evaluate", subject_id, lecture_id)

        with self._lock:
            if lkey in self._active_lectures:
                raise RuntimeError(
                    f"A processing or evaluation job is already running for '{subject_id}/{lecture_id}'."
                )
            self._active_lectures.add(lkey)
            job_id = f"eval_{uuid.uuid4().hex[:10]}"
            now = utc_now_iso()
            job_state: Dict[str, Any] = {
                "job_id": job_id,
                "status": "evaluating",
                "stage": "Initializing verification pipeline",
                "stage_index": 0,
                "stage_count": 4,
                "message": f"Validating {len(student_entries)} student feedback submissions",
                "current": 0,
                "total": len(student_entries),
                "started_at": now,
                "updated_at": now,
                "started_monotonic": time.monotonic(),
                "elapsed_seconds": 0.0,
                "warnings": [],
                "error": None,
                "can_retry": False,
            }
            self._jobs[jkey] = job_state

        self.storage.update_evaluation_state(
            subject_id,
            lecture_id,
            {
                "job_id": job_id,
                "status": "evaluating",
                "stage": job_state["stage"],
                "stage_index": 0,
                "stage_count": 4,
                "error": None,
                "warnings": [],
            },
        )

        def _progress(ev: Dict[str, Any]) -> None:
            with self._lock:
                st = self._jobs.get(jkey)
                if st is not None:
                    st["stage"] = ev.get("stage") or st["stage"]
                    st["stage_index"] = ev.get("stage_index", st["stage_index"])
                    st["stage_count"] = ev.get("stage_count", st["stage_count"])
                    st["message"] = ev.get("message") or st["stage"]
                    st["current"] = ev.get("current")
                    st["total"] = ev.get("total")
                    st["updated_at"] = utc_now_iso()
            self.storage.update_evaluation_state(
                subject_id,
                lecture_id,
                {
                    "status": "evaluating",
                    "stage": ev.get("stage"),
                    "stage_index": ev.get("stage_index", 0),
                    "stage_count": ev.get("stage_count", 4),
                },
            )

        def _worker() -> None:
            t0 = time.monotonic()
            stats_before = snapshot_llm_stats()
            try:
                if overwrite_existing and res_dir.exists():
                    shutil.rmtree(res_dir)

                summary = run_verification_pipeline(
                    course_id=subject_id,
                    lecture_id=lecture_id,
                    feedback_csv=csv_path,
                    student_id_column=id_col,
                    feedback_column=fb_col,
                    top_k=top_k,
                    data_root=self.storage.data_root,
                    strict_llm=strict_llm,
                    progress_callback=_progress,
                )
                stats_after = snapshot_llm_stats()
                fallbacks_used = max(
                    0,
                    int(stats_after.get("fallbacks", 0)) - int(stats_before.get("fallbacks", 0)),
                )
                warnings: List[str] = []
                if fallbacks_used > 0:
                    last_err = stats_after.get("last_error")
                    detail_note = f" ({last_err})" if last_err else ""
                    warnings.append(
                        f"LLM API unavailable/quota reached on {fallbacks_used} request(s); "
                        f"deterministic lexical & semantic lecture verification fallback was used.{detail_note}"
                    )

                elapsed = round(time.monotonic() - t0, 2)
                done_iso = utc_now_iso()
                done_state = {
                    "job_id": job_id,
                    "status": "completed",
                    "stage": "Evaluation complete",
                    "stage_index": 4,
                    "stage_count": 4,
                    "message": (
                        f"Evaluated {summary['total_students']} students "
                        f"(Class average: {summary['average_total_score']}/10)"
                    ),
                    "current": summary["total_students"],
                    "total": summary["total_students"],
                    "total_students": summary["total_students"],
                    "average_total_score": summary["average_total_score"],
                    "last_evaluated_at": done_iso,
                    "elapsed_seconds": elapsed,
                    "outdated": False,
                    "warnings": warnings,
                    "error": None,
                    "can_retry": False,
                }
                self.storage.update_evaluation_state(subject_id, lecture_id, done_state)
                with self._lock:
                    self._jobs[jkey] = dict(done_state)
            except Exception as exc:
                safe_err = redact_secrets(str(exc))
                elapsed = round(time.monotonic() - t0, 2)
                fail_state = {
                    "job_id": job_id,
                    "status": "failed",
                    "stage": "Evaluation failed",
                    "message": safe_err,
                    "error": safe_err,
                    "elapsed_seconds": elapsed,
                    "can_retry": True,
                }
                self.storage.update_evaluation_state(subject_id, lecture_id, fail_state)
                with self._lock:
                    if jkey in self._jobs:
                        self._jobs[jkey].update(fail_state)
            finally:
                with self._lock:
                    self._active_lectures.discard(lkey)

        self._executor.submit(_worker)
        return self.get_job_status("evaluate", subject_id, lecture_id)
