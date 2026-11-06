import csv
import io
import json
import os
import re
import shutil
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from backend.common.paths import (
    SUPPORTED_AUDIO_EXTENSIONS,
    SUPPORTED_DOCUMENT_EXTENSIONS,
    compute_file_sha256,
    get_data_root,
    get_lecture_paths,
    get_results_dir,
    sanitize_student_id,
    validate_identifier,
    validate_non_empty_text,
)
from backend.verification.scorer import (
    ACCURACY_MAX,
    COVERAGE_MAX,
    GRADE_BANDS,
    UNDERSTANDING_MAX,
    compute_grade,
)

MAX_AUDIO_BYTES = 500 * 1024 * 1024      # 500 MB
MAX_DOCUMENT_BYTES = 150 * 1024 * 1024   # 150 MB
MAX_CSV_BYTES = 50 * 1024 * 1024         # 50 MB

DEFAULT_TEACHERS: List[Dict[str, Any]] = [
    {
        "teacher_id": "t_workspace",
        "name": "Prof. Workspace Faculty",
        "department": "General & Imported Lectures",
        "avatar_initials": "WF",
        "created_at": "2026-01-01T00:00:00+00:00",
    },
    {
        "teacher_id": "t_sharma",
        "name": "Dr. Ananya Sharma",
        "department": "Database & Data Systems",
        "avatar_initials": "AS",
        "created_at": "2026-01-01T00:00:00+00:00",
    },
    {
        "teacher_id": "t_verma",
        "name": "Prof. Rajesh Verma",
        "department": "Systems & Operating Environments",
        "avatar_initials": "RV",
        "created_at": "2026-01-01T00:00:00+00:00",
    },
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_seconds_mmss(seconds: Optional[float]) -> Optional[str]:
    if seconds is None:
        return None
    try:
        total = max(0, int(round(float(seconds))))
        mins, secs = divmod(total, 60)
        hrs, mins = divmod(mins, 60)
        if hrs > 0:
            return f"{hrs:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"
    except Exception:
        return None


def safe_upload_filename(original_name: Optional[str], default_stem: str = "uploaded_file") -> str:
    """Sanitizes an arbitrary uploaded filename while preserving its readable name and extension."""
    raw = (original_name or "").strip()
    # Strip any directory components sent by browsers/clients
    raw = raw.replace("\\", "/").split("/")[-1].strip()
    if not raw:
        raise ValueError("Uploaded filename cannot be empty.")

    p = Path(raw)
    ext = p.suffix.lower()
    stem = p.stem.strip()
    safe_stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem).strip(" .")
    if not safe_stem:
        safe_stem = default_stem
    return f"{safe_stem}{ext}"


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def _read_json_if_exists(path: Path) -> Optional[Any]:
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


class LocalWorkspaceStorage:
    """
    Thread-safe local filesystem storage manager (NO database).
    Maintains `workspace_registry.json` and per-lecture `lecture.json` manifests,
    automatically discovering pre-existing lecture folders on disk.
    """

    def __init__(self, data_root: Optional[Union[str, Path]] = None) -> None:
        self._explicit_data_root = Path(data_root).resolve() if data_root is not None else None
        self._lock = threading.RLock()

    @property
    def data_root(self) -> Path:
        root = get_data_root(self._explicit_data_root)
        root.mkdir(parents=True, exist_ok=True)
        return root

    @property
    def registry_path(self) -> Path:
        return self.data_root / "workspace_registry.json"

    def _default_registry(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "updated_at": utc_now_iso(),
            "teachers": [dict(t) for t in DEFAULT_TEACHERS],
            "subjects": {},
        }

    def _load_raw_registry(self) -> Dict[str, Any]:
        loaded = _read_json_if_exists(self.registry_path)
        if not isinstance(loaded, dict):
            reg = self._default_registry()
            _atomic_write_json(self.registry_path, reg)
            return reg

        if "teachers" not in loaded or not isinstance(loaded["teachers"], list) or not loaded["teachers"]:
            loaded["teachers"] = [dict(t) for t in DEFAULT_TEACHERS]
        else:
            existing_tids = {t.get("teacher_id") for t in loaded["teachers"] if isinstance(t, dict)}
            for dt in DEFAULT_TEACHERS:
                if dt["teacher_id"] not in existing_tids:
                    loaded["teachers"].append(dict(dt))

        if "subjects" not in loaded or not isinstance(loaded["subjects"], dict):
            loaded["subjects"] = {}

        return loaded

    def _save_registry(self, reg: Dict[str, Any]) -> None:
        reg["updated_at"] = utc_now_iso()
        _atomic_write_json(self.registry_path, reg)

    def _write_lecture_manifest(self, subject_id: str, chapter: Dict[str, Any]) -> None:
        lpaths = get_lecture_paths(subject_id, chapter["lecture_id"], data_root=self.data_root)
        if lpaths.lecture_dir.exists():
            _atomic_write_json(lpaths.manifest, chapter)

    def _probe_kb_ready(self, subject_id: str, lecture_id: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        lpaths = get_lecture_paths(subject_id, lecture_id, data_root=self.data_root)
        kb_exists = (
            lpaths.faiss_index.is_file()
            and lpaths.embeddings.is_file()
            and lpaths.chunk_mapping.is_file()
        )
        meta = _read_json_if_exists(lpaths.dataset_metadata)
        return kb_exists, meta if isinstance(meta, dict) else None

    def _probe_raw_files(self, raw_dir: Path) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        audio_rec: Optional[Dict[str, Any]] = None
        doc_rec: Optional[Dict[str, Any]] = None
        if not raw_dir.is_dir():
            return None, None

        for item in sorted(raw_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not item.is_file() or item.stat().st_size == 0:
                continue
            ext = item.suffix.lower()
            stat = item.stat()
            uploaded_iso = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            if audio_rec is None and ext in SUPPORTED_AUDIO_EXTENSIONS:
                audio_rec = {
                    "filename": item.name,
                    "original_filename": item.name,
                    "extension": ext,
                    "size_bytes": stat.st_size,
                    "uploaded_at": uploaded_iso,
                    "upload_status": "uploaded",
                    "sha256": compute_file_sha256(item),
                }
            elif doc_rec is None and ext in SUPPORTED_DOCUMENT_EXTENSIONS:
                doc_rec = {
                    "filename": item.name,
                    "original_filename": item.name,
                    "extension": ext,
                    "size_bytes": stat.st_size,
                    "uploaded_at": uploaded_iso,
                    "upload_status": "uploaded",
                    "sha256": compute_file_sha256(item),
                }
        return audio_rec, doc_rec

    def _probe_results_summary(self, subject_id: str, lecture_id: str) -> Optional[Dict[str, Any]]:
        res_dir = get_results_dir(subject_id, lecture_id, data_root=self.data_root)
        summary_path = res_dir / "all_students_summary.json"
        summary = _read_json_if_exists(summary_path)
        if isinstance(summary, dict) and isinstance(summary.get("students"), list):
            return summary
        return None

    def sync_with_filesystem(self) -> Dict[str, Any]:
        """
        Synchronizes `workspace_registry.json` with actual lecture and results directories on disk.
        Ensures any CLI-ingested lectures (such as AI/AI_lect1 or python/python_lect1) are automatically
        registered and that file/KB/result statuses accurately reflect filesystem state.
        """
        with self._lock:
            reg = self._load_raw_registry()
            lectures_root = self.data_root / "lectures"
            dirty = False
            default_teacher_id = reg["teachers"][0]["teacher_id"]

            # 1. Auto-discover subject/lecture folders created via CLI or restored on disk
            if lectures_root.is_dir():
                for subj_dir in sorted(lectures_root.iterdir()):
                    if not subj_dir.is_dir():
                        continue
                    try:
                        subject_id = validate_identifier(subj_dir.name, "course_id")
                    except ValueError:
                        continue

                    subj_rec = reg["subjects"].get(subject_id)
                    if subj_rec is None:
                        subj_rec = {
                            "subject_id": subject_id,
                            "name": subject_id,
                            "teacher_id": default_teacher_id,
                            "next_lecture_seq": 1,
                            "created_at": utc_now_iso(),
                            "updated_at": utc_now_iso(),
                            "chapters": {},
                        }
                        reg["subjects"][subject_id] = subj_rec
                        dirty = True

                    for lect_dir in sorted(subj_dir.iterdir()):
                        if not lect_dir.is_dir():
                            continue
                        try:
                            lecture_id = validate_identifier(lect_dir.name, "lecture_id")
                        except ValueError:
                            continue

                        kb_ready, meta = self._probe_kb_ready(subject_id, lecture_id)
                        if meta and meta.get("course_name") and subj_rec["name"] == subject_id:
                            subj_rec["name"] = str(meta["course_name"]).strip() or subject_id
                            dirty = True

                        # Advance sequence counter past any discovered {subject_id}_lect{N}
                        m = re.match(rf"^{re.escape(subject_id)}_lect(\d+)$", lecture_id)
                        if m:
                            seq_num = int(m.group(1))
                            if subj_rec.get("next_lecture_seq", 1) <= seq_num:
                                subj_rec["next_lecture_seq"] = seq_num + 1
                                dirty = True

                        if lecture_id not in subj_rec["chapters"]:
                            manifest = _read_json_if_exists(lect_dir / "lecture.json")
                            audio_rec, doc_rec = self._probe_raw_files(lect_dir / "raw")
                            summary = self._probe_results_summary(subject_id, lecture_id)
                            title = (
                                (manifest.get("title") if isinstance(manifest, dict) else None)
                                or (meta.get("lecture_title") if meta else None)
                                or lecture_id
                            )
                            chapter_rec: Dict[str, Any] = {
                                "lecture_id": lecture_id,
                                "subject_id": subject_id,
                                "title": title,
                                "created_at": (
                                    manifest.get("created_at")
                                    if isinstance(manifest, dict) and manifest.get("created_at")
                                    else utc_now_iso()
                                ),
                                "updated_at": utc_now_iso(),
                                "files": {
                                    "audio": audio_rec,
                                    "document": doc_rec,
                                    "feedback_csv": (
                                        manifest.get("files", {}).get("feedback_csv")
                                        if isinstance(manifest, dict)
                                        else None
                                    ),
                                },
                                "processing": {
                                    "status": "completed" if kb_ready else "not_started",
                                    "stage": "Knowledge base ready" if kb_ready else None,
                                    "stage_index": 5 if kb_ready else 0,
                                    "stage_count": 5,
                                    "whisper_model": (
                                        meta.get("processing_config", {}).get("whisper_model", "base")
                                        if meta
                                        else "base"
                                    ),
                                    "transcript_chunks": meta.get("total_transcript_chunks", 0) if meta else 0,
                                    "pdf_chunks": meta.get("total_pdf_chunks", 0) if meta else 0,
                                    "total_chunks": meta.get("total_chunks", 0) if meta else 0,
                                    "lecture_concepts_count": len(meta.get("lecture_concepts", [])) if meta else 0,
                                    "last_processed_at": utc_now_iso() if kb_ready else None,
                                    "outdated_reason": None,
                                    "error": None,
                                },
                                "evaluation": {
                                    "status": "completed" if summary else "not_started",
                                    "stage": "Evaluation complete" if summary else None,
                                    "stage_index": 4 if summary else 0,
                                    "stage_count": 4,
                                    "total_students": summary.get("total_students", 0) if summary else 0,
                                    "average_total_score": summary.get("average_total_score") if summary else None,
                                    "last_evaluated_at": utc_now_iso() if summary else None,
                                    "outdated": False,
                                    "warnings": [],
                                    "error": None,
                                },
                            }
                            subj_rec["chapters"][lecture_id] = chapter_rec
                            self._write_lecture_manifest(subject_id, chapter_rec)
                            dirty = True

            # 2. Reconcile existing registered chapters with filesystem reality
            for subject_id, subj_rec in list(reg["subjects"].items()):
                chapters = subj_rec.get("chapters", {})
                for lecture_id, ch in list(chapters.items()):
                    lpaths = get_lecture_paths(subject_id, lecture_id, data_root=self.data_root)
                    kb_ready, meta = self._probe_kb_ready(subject_id, lecture_id)
                    summary = self._probe_results_summary(subject_id, lecture_id)

                    # Verify raw files still exist if recorded
                    files_dict = ch.setdefault("files", {"audio": None, "document": None, "feedback_csv": None})
                    for fk, subdir in (
                        ("audio", lpaths.raw_dir),
                        ("document", lpaths.raw_dir),
                        ("feedback_csv", lpaths.inputs_dir),
                    ):
                        fmeta = files_dict.get(fk)
                        if isinstance(fmeta, dict) and fmeta.get("filename"):
                            fpath = subdir / fmeta["filename"]
                            if not fpath.is_file():
                                files_dict[fk] = None
                                dirty = True

                    # Discover raw files added via CLI if missing from record
                    if files_dict.get("audio") is None or files_dict.get("document") is None:
                        disk_audio, disk_doc = self._probe_raw_files(lpaths.raw_dir)
                        if files_dict.get("audio") is None and disk_audio is not None:
                            files_dict["audio"] = disk_audio
                            dirty = True
                        if files_dict.get("document") is None and disk_doc is not None:
                            files_dict["document"] = disk_doc
                            dirty = True

                    proc = ch.setdefault("processing", {})
                    cur_pstatus = proc.get("status", "not_started")
                    if kb_ready and meta:
                        proc["transcript_chunks"] = meta.get("total_transcript_chunks", 0)
                        proc["pdf_chunks"] = meta.get("total_pdf_chunks", 0)
                        proc["total_chunks"] = meta.get("total_chunks", 0)
                        proc["lecture_concepts_count"] = len(meta.get("lecture_concepts", []))
                        if cur_pstatus == "not_started":
                            proc["status"] = "completed"
                            proc["stage"] = "Knowledge base ready"
                            dirty = True
                    elif not kb_ready and cur_pstatus in ("completed", "outdated"):
                        proc["status"] = "not_started"
                        proc["total_chunks"] = 0
                        dirty = True

                    ev = ch.setdefault("evaluation", {})
                    cur_estatus = ev.get("status", "not_started")
                    if summary:
                        ev["total_students"] = summary.get("total_students", 0)
                        ev["average_total_score"] = summary.get("average_total_score")
                        if cur_estatus == "not_started":
                            ev["status"] = "completed"
                            dirty = True
                    elif not summary and cur_estatus == "completed":
                        ev["status"] = "not_started"
                        ev["total_students"] = 0
                        ev["average_total_score"] = None
                        dirty = True

            if dirty:
                self._save_registry(reg)
            return reg

    # =========================================================================
    # TEACHERS
    # =========================================================================

    def list_teachers(self) -> List[Dict[str, Any]]:
        reg = self.sync_with_filesystem()
        teachers = reg["teachers"]
        # Attach subject counts per teacher
        counts: Dict[str, int] = {}
        for subj in reg["subjects"].values():
            tid = subj.get("teacher_id", teachers[0]["teacher_id"])
            counts[tid] = counts.get(tid, 0) + 1

        out = []
        for t in teachers:
            item = dict(t)
            item["subject_count"] = counts.get(t["teacher_id"], 0)
            out.append(item)
        return out

    def create_teacher(self, name: str, department: Optional[str] = None) -> Dict[str, Any]:
        clean_name = validate_non_empty_text(name, "Teacher name")
        clean_dept = (department or "Faculty Member").strip() or "Faculty Member"
        words = [w for w in re.split(r"\s+", clean_name) if w and not w.endswith(".")]
        initials = "".join(w[0].upper() for w in (words[:2] if words else [clean_name[:2]]))[:2] or "TC"

        with self._lock:
            reg = self.sync_with_filesystem()
            slug = re.sub(r"[^a-z0-9]+", "_", clean_name.lower()).strip("_") or "teacher"
            existing_ids = {t["teacher_id"] for t in reg["teachers"]}
            candidate = f"t_{slug[:20]}"
            idx = 2
            while candidate in existing_ids:
                candidate = f"t_{slug[:16]}_{idx}"
                idx += 1

            record = {
                "teacher_id": candidate,
                "name": clean_name,
                "department": clean_dept,
                "avatar_initials": initials,
                "created_at": utc_now_iso(),
            }
            reg["teachers"].append(record)
            self._save_registry(reg)
            rec_out = dict(record)
            rec_out["subject_count"] = 0
            return rec_out

    # =========================================================================
    # SUBJECTS
    # =========================================================================

    def _generate_unique_subject_id(
        self,
        name: str,
        code: Optional[str],
        existing_ids: set[str],
    ) -> str:
        lectures_root = self.data_root / "lectures"
        results_root = self.data_root / "results"

        if code and code.strip():
            raw_base = re.sub(r"[^A-Za-z0-9_-]+", "_", code.strip()).strip("_-")
        else:
            cleaned = name.strip()
            if re.fullmatch(r"[A-Za-z0-9_-]{1,18}", cleaned):
                raw_base = cleaned
            else:
                words = [w for w in re.findall(r"[A-Za-z0-9]+", cleaned) if w.lower() not in {"of", "and", "the", "in", "to", "for"}]
                if len(words) >= 2 and all(len(w) >= 2 for w in words):
                    acronym = "".join(w[0].upper() for w in words[:6])
                    raw_base = acronym if len(acronym) >= 2 else "_".join(w.upper() for w in words[:3])
                elif words:
                    raw_base = words[0][:18].upper()
                else:
                    raw_base = "SUBJECT"

        base_id = validate_identifier(raw_base or "SUBJECT", "subject_id")
        candidate = base_id
        seq = 2
        while (
            candidate in existing_ids
            or (lectures_root / candidate).exists()
            or (results_root / candidate).exists()
        ):
            candidate = f"{base_id}_{seq}"
            seq += 1
        return validate_identifier(candidate, "subject_id")

    def _format_subject_summary(self, subj: Dict[str, Any]) -> Dict[str, Any]:
        chapters_list = list(subj.get("chapters", {}).values())
        chapters_list.sort(key=lambda c: c.get("created_at", ""))
        processed_count = sum(
            1 for c in chapters_list if c.get("processing", {}).get("status") in ("completed", "outdated")
        )
        evaluated_count = sum(
            1 for c in chapters_list if c.get("evaluation", {}).get("status") == "completed"
        )
        return {
            "subject_id": subj["subject_id"],
            "name": subj["name"],
            "teacher_id": subj["teacher_id"],
            "created_at": subj.get("created_at"),
            "updated_at": subj.get("updated_at"),
            "chapter_count": len(chapters_list),
            "processed_chapter_count": processed_count,
            "evaluated_chapter_count": evaluated_count,
            "chapters": chapters_list,
        }

    def list_subjects(self, teacher_id: Optional[str] = None) -> List[Dict[str, Any]]:
        reg = self.sync_with_filesystem()
        subjects = list(reg["subjects"].values())
        if teacher_id and teacher_id != "all":
            subjects = [s for s in subjects if s.get("teacher_id") == teacher_id]
        subjects.sort(key=lambda s: s.get("created_at", ""))
        return [self._format_subject_summary(s) for s in subjects]

    def get_subject(self, subject_id: str) -> Dict[str, Any]:
        valid_sid = validate_identifier(subject_id, "subject_id")
        reg = self.sync_with_filesystem()
        subj = reg["subjects"].get(valid_sid)
        if subj is None:
            raise KeyError(f"Subject '{valid_sid}' not found.")
        return self._format_subject_summary(subj)

    def create_subject(
        self,
        name: str,
        teacher_id: str,
        code: Optional[str] = None,
    ) -> Dict[str, Any]:
        clean_name = validate_non_empty_text(name, "Subject name")
        clean_tid = validate_non_empty_text(teacher_id, "teacher_id")

        with self._lock:
            reg = self.sync_with_filesystem()
            valid_tids = {t["teacher_id"] for t in reg["teachers"]}
            if clean_tid not in valid_tids:
                raise KeyError(f"Teacher '{clean_tid}' does not exist.")

            subject_id = self._generate_unique_subject_id(
                name=clean_name,
                code=code,
                existing_ids=set(reg["subjects"].keys()),
            )
            now = utc_now_iso()
            subj_rec = {
                "subject_id": subject_id,
                "name": clean_name,
                "teacher_id": clean_tid,
                "next_lecture_seq": 1,
                "created_at": now,
                "updated_at": now,
                "chapters": {},
            }
            (self.data_root / "lectures" / subject_id).mkdir(parents=True, exist_ok=True)
            reg["subjects"][subject_id] = subj_rec
            self._save_registry(reg)
            return self._format_subject_summary(subj_rec)

    def rename_subject(self, subject_id: str, new_name: str) -> Dict[str, Any]:
        valid_sid = validate_identifier(subject_id, "subject_id")
        clean_name = validate_non_empty_text(new_name, "Subject name")

        with self._lock:
            reg = self.sync_with_filesystem()
            subj = reg["subjects"].get(valid_sid)
            if subj is None:
                raise KeyError(f"Subject '{valid_sid}' not found.")
            subj["name"] = clean_name
            subj["updated_at"] = utc_now_iso()

            # Update course_name inside existing dataset_metadata.json files if present
            for lecture_id in subj.get("chapters", {}):
                lpaths = get_lecture_paths(valid_sid, lecture_id, data_root=self.data_root)
                meta = _read_json_if_exists(lpaths.dataset_metadata)
                if isinstance(meta, dict):
                    meta["course_name"] = clean_name
                    _atomic_write_json(lpaths.dataset_metadata, meta)

            self._save_registry(reg)
            return self._format_subject_summary(subj)

    def delete_subject(self, subject_id: str) -> Dict[str, Any]:
        valid_sid = validate_identifier(subject_id, "subject_id")
        with self._lock:
            reg = self.sync_with_filesystem()
            subj = reg["subjects"].get(valid_sid)
            if subj is None:
                raise KeyError(f"Subject '{valid_sid}' not found.")

            del reg["subjects"][valid_sid]
            self._save_registry(reg)

            subj_lect_dir = self.data_root / "lectures" / valid_sid
            subj_res_dir = self.data_root / "results" / valid_sid
            if subj_lect_dir.exists():
                shutil.rmtree(subj_lect_dir)
            if subj_res_dir.exists():
                shutil.rmtree(subj_res_dir)

            return {"deleted_subject_id": valid_sid, "name": subj["name"]}

    # =========================================================================
    # CHAPTERS / LECTURES
    # =========================================================================

    def _generate_unique_lecture_id(self, subject_id: str, subj_rec: Dict[str, Any]) -> str:
        seq = max(1, int(subj_rec.get("next_lecture_seq", 1)))
        existing_chapters = set(subj_rec.get("chapters", {}).keys())
        lectures_root = self.data_root / "lectures" / subject_id
        results_root = self.data_root / "results" / subject_id

        while True:
            candidate = validate_identifier(f"{subject_id}_lect{seq}", "lecture_id")
            if (
                candidate not in existing_chapters
                and not (lectures_root / candidate).exists()
                and not (results_root / candidate).exists()
            ):
                subj_rec["next_lecture_seq"] = seq + 1
                return candidate
            seq += 1

    def list_chapters(self, subject_id: str) -> List[Dict[str, Any]]:
        subj = self.get_subject(subject_id)
        return subj["chapters"]

    def get_chapter(self, subject_id: str, lecture_id: str) -> Dict[str, Any]:
        valid_sid = validate_identifier(subject_id, "subject_id")
        valid_lid = validate_identifier(lecture_id, "lecture_id")
        reg = self.sync_with_filesystem()
        subj = reg["subjects"].get(valid_sid)
        if subj is None:
            raise KeyError(f"Subject '{valid_sid}' not found.")
        ch = subj.get("chapters", {}).get(valid_lid)
        if ch is None:
            raise KeyError(f"Chapter '{valid_lid}' not found inside subject '{valid_sid}'.")
        out = dict(ch)
        out["subject_name"] = subj["name"]
        out["teacher_id"] = subj["teacher_id"]
        return out

    def create_chapter(self, subject_id: str, title: str) -> Dict[str, Any]:
        valid_sid = validate_identifier(subject_id, "subject_id")
        clean_title = validate_non_empty_text(title, "Chapter title")

        with self._lock:
            reg = self.sync_with_filesystem()
            subj = reg["subjects"].get(valid_sid)
            if subj is None:
                raise KeyError(f"Subject '{valid_sid}' not found.")

            lecture_id = self._generate_unique_lecture_id(valid_sid, subj)
            lpaths = get_lecture_paths(valid_sid, lecture_id, data_root=self.data_root)
            lpaths.ensure_dirs()
            lpaths.inputs_dir.mkdir(parents=True, exist_ok=True)

            now = utc_now_iso()
            chapter_rec: Dict[str, Any] = {
                "lecture_id": lecture_id,
                "subject_id": valid_sid,
                "title": clean_title,
                "created_at": now,
                "updated_at": now,
                "files": {
                    "audio": None,
                    "document": None,
                    "feedback_csv": None,
                },
                "processing": {
                    "status": "not_started",
                    "stage": None,
                    "stage_index": 0,
                    "stage_count": 5,
                    "whisper_model": "base",
                    "transcript_chunks": 0,
                    "pdf_chunks": 0,
                    "total_chunks": 0,
                    "lecture_concepts_count": 0,
                    "last_processed_at": None,
                    "outdated_reason": None,
                    "error": None,
                },
                "evaluation": {
                    "status": "not_started",
                    "stage": None,
                    "stage_index": 0,
                    "stage_count": 4,
                    "total_students": 0,
                    "average_total_score": None,
                    "last_evaluated_at": None,
                    "outdated": False,
                    "warnings": [],
                    "error": None,
                },
            }
            subj["chapters"][lecture_id] = chapter_rec
            subj["updated_at"] = now
            self._write_lecture_manifest(valid_sid, chapter_rec)
            self._save_registry(reg)

            out = dict(chapter_rec)
            out["subject_name"] = subj["name"]
            out["teacher_id"] = subj["teacher_id"]
            return out

    def rename_chapter(self, subject_id: str, lecture_id: str, new_title: str) -> Dict[str, Any]:
        valid_sid = validate_identifier(subject_id, "subject_id")
        valid_lid = validate_identifier(lecture_id, "lecture_id")
        clean_title = validate_non_empty_text(new_title, "Chapter title")

        with self._lock:
            reg = self.sync_with_filesystem()
            subj = reg["subjects"].get(valid_sid)
            if subj is None:
                raise KeyError(f"Subject '{valid_sid}' not found.")
            ch = subj.get("chapters", {}).get(valid_lid)
            if ch is None:
                raise KeyError(f"Chapter '{valid_lid}' not found in subject '{valid_sid}'.")

            ch["title"] = clean_title
            ch["updated_at"] = utc_now_iso()
            subj["updated_at"] = ch["updated_at"]

            lpaths = get_lecture_paths(valid_sid, valid_lid, data_root=self.data_root)
            meta = _read_json_if_exists(lpaths.dataset_metadata)
            if isinstance(meta, dict):
                meta["lecture_title"] = clean_title
                _atomic_write_json(lpaths.dataset_metadata, meta)

            self._write_lecture_manifest(valid_sid, ch)
            self._save_registry(reg)
            out = dict(ch)
            out["subject_name"] = subj["name"]
            out["teacher_id"] = subj["teacher_id"]
            return out

    def delete_chapter(self, subject_id: str, lecture_id: str) -> Dict[str, Any]:
        valid_sid = validate_identifier(subject_id, "subject_id")
        valid_lid = validate_identifier(lecture_id, "lecture_id")

        with self._lock:
            reg = self.sync_with_filesystem()
            subj = reg["subjects"].get(valid_sid)
            if subj is None:
                raise KeyError(f"Subject '{valid_sid}' not found.")
            ch = subj.get("chapters", {}).get(valid_lid)
            if ch is None:
                raise KeyError(f"Chapter '{valid_lid}' not found in subject '{valid_sid}'.")

            del subj["chapters"][valid_lid]
            subj["updated_at"] = utc_now_iso()
            self._save_registry(reg)

            lpaths = get_lecture_paths(valid_sid, valid_lid, data_root=self.data_root)
            res_dir = get_results_dir(valid_sid, valid_lid, data_root=self.data_root)
            if lpaths.lecture_dir.exists():
                shutil.rmtree(lpaths.lecture_dir)
            if res_dir.exists():
                shutil.rmtree(res_dir)

            return {
                "deleted_lecture_id": valid_lid,
                "subject_id": valid_sid,
                "title": ch["title"],
            }

    # =========================================================================
    # FILE UPLOADS & OUTDATED-STATE TRACKING
    # =========================================================================

    def save_lecture_media_file(
        self,
        subject_id: str,
        lecture_id: str,
        kind: str,
        original_filename: str,
        content_bytes: bytes,
    ) -> Dict[str, Any]:
        """
        Validates and permanently saves an uploaded lecture `audio` or `document` (PDF/PPTX)
        inside `backend/data/lectures/{subject_id}/{lecture_id}/raw/`.
        Marks processing/evaluation status as outdated if a KB already existed for this lecture.
        """
        if kind not in ("audio", "document"):
            raise ValueError(f"Invalid lecture file kind '{kind}'.")

        valid_sid = validate_identifier(subject_id, "subject_id")
        valid_lid = validate_identifier(lecture_id, "lecture_id")
        safe_name = safe_upload_filename(original_filename, default_stem=kind)
        ext = Path(safe_name).suffix.lower()

        allowed_exts = SUPPORTED_AUDIO_EXTENSIONS if kind == "audio" else SUPPORTED_DOCUMENT_EXTENSIONS
        max_bytes = MAX_AUDIO_BYTES if kind == "audio" else MAX_DOCUMENT_BYTES
        label = "Audio/video" if kind == "audio" else "Lecture document (PDF/PPTX)"

        if ext not in allowed_exts:
            supported_str = ", ".join(sorted(allowed_exts))
            raise ValueError(
                f"Unsupported {label} format '{ext}' for '{original_filename}'. Supported formats: {supported_str}"
            )

        size_bytes = len(content_bytes)
        if size_bytes == 0:
            raise ValueError(f"Uploaded {label} file '{original_filename}' is empty (0 bytes).")
        if size_bytes > max_bytes:
            raise ValueError(
                f"Uploaded {label} file exceeds maximum allowed size of {max_bytes // (1024 * 1024)} MB."
            )

        with self._lock:
            reg = self.sync_with_filesystem()
            subj = reg["subjects"].get(valid_sid)
            if subj is None:
                raise KeyError(f"Subject '{valid_sid}' not found.")
            ch = subj.get("chapters", {}).get(valid_lid)
            if ch is None:
                raise KeyError(f"Chapter '{valid_lid}' not found in subject '{valid_sid}'.")

            lpaths = get_lecture_paths(valid_sid, valid_lid, data_root=self.data_root)
            lpaths.ensure_dirs()

            # Remove any prior raw file of the SAME category in THIS lecture's raw/ dir only
            prev_rec = ch.get("files", {}).get(kind)
            prev_sha = prev_rec.get("sha256") if isinstance(prev_rec, dict) else None
            for existing in list(lpaths.raw_dir.iterdir()):
                if existing.is_file() and existing.suffix.lower() in allowed_exts:
                    existing.unlink()

            dest_path = lpaths.raw_dir / safe_name
            with open(dest_path, "wb") as f:
                f.write(content_bytes)

            new_sha = compute_file_sha256(dest_path)
            now = utc_now_iso()
            file_record = {
                "filename": safe_name,
                "original_filename": original_filename,
                "extension": ext,
                "size_bytes": size_bytes,
                "uploaded_at": now,
                "upload_status": "uploaded",
                "sha256": new_sha,
            }
            ch.setdefault("files", {})[kind] = file_record
            ch["updated_at"] = now

            # Mark KB outdated if previously processed and file content changed
            proc = ch.setdefault("processing", {})
            if proc.get("status") == "completed" and prev_sha != new_sha:
                proc["status"] = "outdated"
                proc["outdated_reason"] = (
                    f"{label} was replaced ('{safe_name}'). Reprocess this lecture to update its knowledge base."
                )
                ev = ch.setdefault("evaluation", {})
                if ev.get("status") == "completed":
                    ev["outdated"] = True

            self._write_lecture_manifest(valid_sid, ch)
            self._save_registry(reg)
            return self.get_chapter(valid_sid, valid_lid)

    def remove_lecture_file(self, subject_id: str, lecture_id: str, kind: str) -> Dict[str, Any]:
        if kind not in ("audio", "document", "feedback_csv"):
            raise ValueError(f"Unsupported file kind '{kind}'.")

        valid_sid = validate_identifier(subject_id, "subject_id")
        valid_lid = validate_identifier(lecture_id, "lecture_id")

        with self._lock:
            reg = self.sync_with_filesystem()
            subj = reg["subjects"].get(valid_sid)
            if subj is None:
                raise KeyError(f"Subject '{valid_sid}' not found.")
            ch = subj.get("chapters", {}).get(valid_lid)
            if ch is None:
                raise KeyError(f"Chapter '{valid_lid}' not found in subject '{valid_sid}'.")

            lpaths = get_lecture_paths(valid_sid, valid_lid, data_root=self.data_root)
            rec = ch.get("files", {}).get(kind)
            if isinstance(rec, dict) and rec.get("filename"):
                target_dir = lpaths.inputs_dir if kind == "feedback_csv" else lpaths.raw_dir
                fpath = target_dir / rec["filename"]
                if fpath.is_file():
                    fpath.unlink()

            ch.setdefault("files", {})[kind] = None
            ch["updated_at"] = utc_now_iso()

            if kind in ("audio", "document"):
                proc = ch.setdefault("processing", {})
                if proc.get("status") == "completed":
                    proc["status"] = "outdated"
                    proc["outdated_reason"] = (
                        f"Source {kind} file was removed. Upload replacement or reprocess in single-source mode."
                    )
                    ev = ch.setdefault("evaluation", {})
                    if ev.get("status") == "completed":
                        ev["outdated"] = True

            self._write_lecture_manifest(valid_sid, ch)
            self._save_registry(reg)
            return self.get_chapter(valid_sid, valid_lid)

    # =========================================================================
    # FEEDBACK CSV UPLOAD, PREVIEW & VALIDATION
    # =========================================================================

    @staticmethod
    def _guess_columns(headers: List[str]) -> Tuple[str, str]:
        id_candidates = ["roll_number", "student_id", "roll_no", "roll", "id", "reg_no", "student_code"]
        fb_candidates = ["feedback", "reflection", "student_feedback", "response", "summary", "comments", "notes"]

        lower_map = {h.lower().strip(): h for h in headers}
        chosen_id = ""
        chosen_fb = ""

        for cand in id_candidates:
            if cand in lower_map:
                chosen_id = lower_map[cand]
                break
        if not chosen_id:
            for h in headers:
                if any(tok in h.lower() for tok in ("roll", "id", "reg", "code")):
                    chosen_id = h
                    break
        if not chosen_id and headers:
            chosen_id = headers[0]

        for cand in fb_candidates:
            if cand in lower_map and lower_map[cand] != chosen_id:
                chosen_fb = lower_map[cand]
                break
        if not chosen_fb:
            for h in headers:
                if h != chosen_id and any(tok in h.lower() for tok in ("feedback", "reflect", "resp", "comment", "text")):
                    chosen_fb = h
                    break
        if not chosen_fb:
            remaining = [h for h in headers if h != chosen_id]
            chosen_fb = remaining[0] if remaining else (headers[0] if headers else "")

        return chosen_id, chosen_fb

    @staticmethod
    def inspect_csv_file(
        csv_path: Path,
        student_id_column: Optional[str] = None,
        feedback_column: Optional[str] = None,
        preview_limit: int = 25,
    ) -> Dict[str, Any]:
        if not csv_path.is_file():
            raise FileNotFoundError(f"Feedback CSV file not found at: {csv_path}")

        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            headers = [h for h in (reader.fieldnames or []) if h is not None and h.strip() != ""]
            rows = list(reader)

        if not headers:
            raise ValueError(f"CSV file '{csv_path.name}' contains no valid column headers.")

        auto_id_col, auto_fb_col = LocalWorkspaceStorage._guess_columns(headers)
        sel_id_col = student_id_column if student_id_column is not None else auto_id_col
        sel_fb_col = feedback_column if feedback_column is not None else auto_fb_col

        errors: List[str] = []
        empty_feedback_rows: List[int] = []
        duplicate_ids: List[str] = []
        collision_ids: List[str] = []
        valid_count = 0

        if sel_id_col not in headers:
            errors.append(
                f"Selected Student ID column '{sel_id_col}' not found in CSV headers: {headers}"
            )
        if sel_fb_col not in headers:
            errors.append(
                f"Selected Feedback column '{sel_fb_col}' not found in CSV headers: {headers}"
            )
        if sel_id_col and sel_id_col == sel_fb_col:
            errors.append("Student ID column and Feedback column must be two distinct columns.")

        if not rows:
            errors.append(f"CSV file '{csv_path.name}' contains 0 student rows.")

        if not errors:
            seen_raw: Dict[str, int] = {}
            seen_sanitized: Dict[str, Tuple[str, int]] = {}
            for row_num, row in enumerate(rows, start=2):
                raw_id = (row.get(sel_id_col) or "").strip()
                raw_fb = (row.get(sel_fb_col) or "").strip()

                if not raw_id:
                    errors.append(f"Row {row_num}: empty student identifier in column '{sel_id_col}'.")
                    continue

                try:
                    safe_id = sanitize_student_id(raw_id)
                except ValueError as exc:
                    errors.append(f"Row {row_num}: {exc}")
                    continue

                if raw_id in seen_raw:
                    duplicate_ids.append(raw_id)
                    errors.append(
                        f"Row {row_num}: duplicate student ID '{raw_id}' (first seen on row {seen_raw[raw_id]})."
                    )
                    continue

                if safe_id in seen_sanitized:
                    prev_raw, prev_row = seen_sanitized[safe_id]
                    collision_ids.append(f"{raw_id} <-> {prev_raw}")
                    errors.append(
                        f"Row {row_num}: student ID '{raw_id}' collides with '{prev_raw}' (row {prev_row}) "
                        f"under directory name '{safe_id}'."
                    )
                    continue

                if not raw_fb:
                    empty_feedback_rows.append(row_num)
                    errors.append(
                        f"Row {row_num}: empty feedback text for student '{raw_id}' in column '{sel_fb_col}'."
                    )
                    continue

                seen_raw[raw_id] = row_num
                seen_sanitized[safe_id] = (raw_id, row_num)
                valid_count += 1

        preview_rows = []
        for idx, r in enumerate(rows[:preview_limit], start=1):
            clean_row = {h: (r.get(h) or "") for h in headers}
            preview_rows.append({"row_number": idx + 1, "values": clean_row})

        return {
            "filename": csv_path.name,
            "headers": headers,
            "total_rows": len(rows),
            "preview_rows": preview_rows,
            "student_id_column": sel_id_col,
            "feedback_column": sel_fb_col,
            "validation": {
                "is_valid": len(errors) == 0 and valid_count > 0,
                "valid_student_count": valid_count,
                "errors": errors[:25],
                "total_error_count": len(errors),
                "empty_feedback_rows": empty_feedback_rows,
                "duplicate_ids": duplicate_ids,
                "collision_ids": collision_ids,
            },
        }

    def save_feedback_csv(
        self,
        subject_id: str,
        lecture_id: str,
        original_filename: str,
        content_bytes: bytes,
    ) -> Dict[str, Any]:
        valid_sid = validate_identifier(subject_id, "subject_id")
        valid_lid = validate_identifier(lecture_id, "lecture_id")
        safe_name = safe_upload_filename(original_filename, default_stem="student_feedback")
        ext = Path(safe_name).suffix.lower()

        if ext != ".csv":
            raise ValueError(f"Unsupported feedback file format '{ext}' for '{original_filename}'. Expected '.csv'.")
        if len(content_bytes) == 0:
            raise ValueError(f"Uploaded feedback CSV '{original_filename}' is empty (0 bytes).")
        if len(content_bytes) > MAX_CSV_BYTES:
            raise ValueError("Uploaded feedback CSV exceeds 50 MB limit.")

        with self._lock:
            reg = self.sync_with_filesystem()
            subj = reg["subjects"].get(valid_sid)
            if subj is None:
                raise KeyError(f"Subject '{valid_sid}' not found.")
            ch = subj.get("chapters", {}).get(valid_lid)
            if ch is None:
                raise KeyError(f"Chapter '{valid_lid}' not found in subject '{valid_sid}'.")

            lpaths = get_lecture_paths(valid_sid, valid_lid, data_root=self.data_root)
            lpaths.inputs_dir.mkdir(parents=True, exist_ok=True)

            # Remove previous CSV in this chapter's inputs_dir
            for old_f in list(lpaths.inputs_dir.iterdir()):
                if old_f.is_file() and old_f.suffix.lower() == ".csv":
                    old_f.unlink()

            dest_csv = lpaths.inputs_dir / safe_name
            with open(dest_csv, "wb") as f:
                f.write(content_bytes)

            try:
                inspection = self.inspect_csv_file(dest_csv)
            except Exception:
                if dest_csv.exists():
                    dest_csv.unlink()
                raise

            now = utc_now_iso()
            csv_record = {
                "filename": safe_name,
                "original_filename": original_filename,
                "size_bytes": len(content_bytes),
                "uploaded_at": now,
                "upload_status": "uploaded",
                "sha256": compute_file_sha256(dest_csv),
                "headers": inspection["headers"],
                "total_rows": inspection["total_rows"],
                "student_id_column": inspection["student_id_column"],
                "feedback_column": inspection["feedback_column"],
                "confirmed": False,
                "is_valid": inspection["validation"]["is_valid"],
            }
            ch.setdefault("files", {})["feedback_csv"] = csv_record
            ch["updated_at"] = now
            self._write_lecture_manifest(valid_sid, ch)
            self._save_registry(reg)

            return {
                "chapter": self.get_chapter(valid_sid, valid_lid),
                "preview": inspection,
            }

    def get_feedback_preview(
        self,
        subject_id: str,
        lecture_id: str,
        student_id_column: Optional[str] = None,
        feedback_column: Optional[str] = None,
    ) -> Dict[str, Any]:
        ch = self.get_chapter(subject_id, lecture_id)
        csv_rec = ch.get("files", {}).get("feedback_csv")
        if not isinstance(csv_rec, dict) or not csv_rec.get("filename"):
            raise FileNotFoundError(
                f"No student feedback CSV has been uploaded for {subject_id}/{lecture_id}."
            )
        lpaths = get_lecture_paths(subject_id, lecture_id, data_root=self.data_root)
        csv_path = lpaths.inputs_dir / csv_rec["filename"]
        id_col = student_id_column or csv_rec.get("student_id_column")
        fb_col = feedback_column or csv_rec.get("feedback_column")
        inspection = self.inspect_csv_file(csv_path, student_id_column=id_col, feedback_column=fb_col)
        inspection["confirmed"] = bool(
            csv_rec.get("confirmed")
            and csv_rec.get("student_id_column") == inspection["student_id_column"]
            and csv_rec.get("feedback_column") == inspection["feedback_column"]
            and inspection["validation"]["is_valid"]
        )
        return inspection

    def confirm_feedback_mapping(
        self,
        subject_id: str,
        lecture_id: str,
        student_id_column: str,
        feedback_column: str,
    ) -> Dict[str, Any]:
        valid_sid = validate_identifier(subject_id, "subject_id")
        valid_lid = validate_identifier(lecture_id, "lecture_id")

        with self._lock:
            reg = self.sync_with_filesystem()
            subj = reg["subjects"].get(valid_sid)
            if subj is None:
                raise KeyError(f"Subject '{valid_sid}' not found.")
            ch = subj.get("chapters", {}).get(valid_lid)
            if ch is None:
                raise KeyError(f"Chapter '{valid_lid}' not found in subject '{valid_sid}'.")

            csv_rec = ch.get("files", {}).get("feedback_csv")
            if not isinstance(csv_rec, dict) or not csv_rec.get("filename"):
                raise FileNotFoundError("Upload a feedback CSV before confirming column mapping.")

            lpaths = get_lecture_paths(valid_sid, valid_lid, data_root=self.data_root)
            csv_path = lpaths.inputs_dir / csv_rec["filename"]
            inspection = self.inspect_csv_file(
                csv_path,
                student_id_column=student_id_column,
                feedback_column=feedback_column,
            )
            if not inspection["validation"]["is_valid"]:
                first_err = (
                    inspection["validation"]["errors"][0]
                    if inspection["validation"]["errors"]
                    else "CSV validation failed."
                )
                raise ValueError(first_err)

            csv_rec["student_id_column"] = student_id_column
            csv_rec["feedback_column"] = feedback_column
            csv_rec["confirmed"] = True
            csv_rec["is_valid"] = True
            ch["updated_at"] = utc_now_iso()
            self._write_lecture_manifest(valid_sid, ch)
            self._save_registry(reg)

            inspection["confirmed"] = True
            return {
                "chapter": self.get_chapter(valid_sid, valid_lid),
                "preview": inspection,
            }

    # =========================================================================
    # JOB STATE PERSISTENCE HOOKS
    # =========================================================================

    def update_processing_state(
        self,
        subject_id: str,
        lecture_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        valid_sid = validate_identifier(subject_id, "subject_id")
        valid_lid = validate_identifier(lecture_id, "lecture_id")
        with self._lock:
            reg = self._load_raw_registry()
            subj = reg["subjects"].get(valid_sid)
            if subj and valid_lid in subj.get("chapters", {}):
                ch = subj["chapters"][valid_lid]
                proc = ch.setdefault("processing", {})
                proc.update(updates)
                ch["updated_at"] = utc_now_iso()
                self._write_lecture_manifest(valid_sid, ch)
                self._save_registry(reg)
                return dict(proc)
        return dict(updates)

    def update_evaluation_state(
        self,
        subject_id: str,
        lecture_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        valid_sid = validate_identifier(subject_id, "subject_id")
        valid_lid = validate_identifier(lecture_id, "lecture_id")
        with self._lock:
            reg = self._load_raw_registry()
            subj = reg["subjects"].get(valid_sid)
            if subj and valid_lid in subj.get("chapters", {}):
                ch = subj["chapters"][valid_lid]
                ev = ch.setdefault("evaluation", {})
                ev.update(updates)
                ch["updated_at"] = utc_now_iso()
                self._write_lecture_manifest(valid_sid, ch)
                self._save_registry(reg)
                return dict(ev)
        return dict(updates)

    # =========================================================================
    # METADATA, RESULTS & REPORTS
    # =========================================================================

    def get_lecture_metadata(self, subject_id: str, lecture_id: str) -> Dict[str, Any]:
        ch = self.get_chapter(subject_id, lecture_id)
        lpaths = get_lecture_paths(subject_id, lecture_id, data_root=self.data_root)
        meta = _read_json_if_exists(lpaths.dataset_metadata)
        kb_ready, _ = self._probe_kb_ready(subject_id, lecture_id)
        return {
            "subject_id": ch["subject_id"],
            "subject_name": ch["subject_name"],
            "lecture_id": ch["lecture_id"],
            "lecture_title": ch["title"],
            "kb_ready": kb_ready,
            "processing": ch.get("processing", {}),
            "paths": {
                "lecture_dir": str(lpaths.lecture_dir),
                "knowledge_base_dir": str(lpaths.knowledge_base_dir),
                "faiss_index": str(lpaths.faiss_index),
                "embeddings": str(lpaths.embeddings),
                "chunk_mapping": str(lpaths.chunk_mapping),
                "dataset_metadata": str(lpaths.dataset_metadata),
            },
            "dataset_metadata": meta,
        }

    def get_lecture_results(self, subject_id: str, lecture_id: str) -> Dict[str, Any]:
        ch = self.get_chapter(subject_id, lecture_id)
        res_dir = get_results_dir(subject_id, lecture_id, data_root=self.data_root)
        summary_path = res_dir / "all_students_summary.json"
        summary = _read_json_if_exists(summary_path)
        if not isinstance(summary, dict):
            raise FileNotFoundError(
                f"No evaluation results found for lecture '{subject_id}/{lecture_id}'. Run evaluation first."
            )

        students = summary.get("students", [])
        grade_counts = {label: 0 for _, label in GRADE_BANDS}
        for s in students:
            s["grade"] = s.get("grade") or compute_grade(float(s.get("total_score", 0.0)))
            grade_counts[s["grade"]] = grade_counts.get(s["grade"], 0) + 1

        n = len(students)
        avg_acc = round(sum(float(s.get("accuracy_score", 0)) for s in students) / n, 2) if n else 0.0
        avg_cov = round(sum(float(s.get("coverage_score", 0)) for s in students) / n, 2) if n else 0.0
        avg_und = round(sum(float(s.get("understanding_score", 0)) for s in students) / n, 2) if n else 0.0
        avg_tot = round(sum(float(s.get("total_score", 0)) for s in students) / n, 2) if n else 0.0

        lpaths = get_lecture_paths(subject_id, lecture_id, data_root=self.data_root)
        meta = _read_json_if_exists(lpaths.dataset_metadata)
        concepts = meta.get("lecture_concepts", []) if isinstance(meta, dict) else []

        return {
            "subject_id": ch["subject_id"],
            "subject_name": ch["subject_name"],
            "lecture_id": ch["lecture_id"],
            "lecture_title": ch["title"],
            "results_dir": str(res_dir),
            "evaluation": ch.get("evaluation", {}),
            "processing": ch.get("processing", {}),
            "rubric": {
                "factual_accuracy_max": ACCURACY_MAX,
                "lecture_coverage_max": COVERAGE_MAX,
                "understanding_quality_max": UNDERSTANDING_MAX,
                "total_max": ACCURACY_MAX + COVERAGE_MAX + UNDERSTANDING_MAX,
                "grade_bands": [{"min_score": lo, "grade": g} for lo, g in GRADE_BANDS],
            },
            "total_students": n,
            "averages": {
                "accuracy_score": avg_acc,
                "coverage_score": avg_cov,
                "understanding_score": avg_und,
                "total_score": avg_tot,
                "average_grade": compute_grade(avg_tot) if n else "N/A",
            },
            "grade_distribution": grade_counts,
            "lecture_concepts": concepts,
            "students": students,
        }

    def get_student_result_detail(
        self,
        subject_id: str,
        lecture_id: str,
        student_identifier: str,
    ) -> Dict[str, Any]:
        ch = self.get_chapter(subject_id, lecture_id)
        res_dir = get_results_dir(subject_id, lecture_id, data_root=self.data_root)
        summary = _read_json_if_exists(res_dir / "all_students_summary.json")

        target_dir: Optional[Path] = None
        if isinstance(summary, dict):
            for entry in summary.get("students", []):
                if student_identifier in (entry.get("student_id"), entry.get("sanitized_student_id")):
                    cand = res_dir / str(entry.get("sanitized_student_id"))
                    if cand.is_dir():
                        target_dir = cand
                        break

        if target_dir is None:
            safe_id = sanitize_student_id(student_identifier)
            cand = res_dir / safe_id
            if cand.is_dir():
                target_dir = cand

        if target_dir is None or not (target_dir / "score.json").is_file():
            raise KeyError(
                f"Results for student '{student_identifier}' not found under {subject_id}/{lecture_id}."
            )

        score_data = _read_json_if_exists(target_dir / "score.json") or {}
        claims_data = _read_json_if_exists(target_dir / "claims.json") or {}
        evaluated_data = _read_json_if_exists(target_dir / "evaluated.json") or {}

        score_data["grade"] = score_data.get("grade") or compute_grade(
            float(score_data.get("scores", {}).get("total", {}).get("score", 0.0))
        )

        # Format timestamps & page numbers cleanly on every evidence item
        claims_list = score_data.get("evaluated_claims") or evaluated_data.get("claims") or []
        for cl in claims_list:
            for ev in cl.get("evidence", []):
                st = ev.get("start_time")
                et = ev.get("end_time")
                if st is not None or et is not None:
                    ev["timestamp_range"] = f"{format_seconds_mmss(st) or '00:00'} - {format_seconds_mmss(et) or '00:00'}"
                else:
                    ev["timestamp_range"] = None

        return {
            "subject_id": ch["subject_id"],
            "subject_name": ch["subject_name"],
            "lecture_id": ch["lecture_id"],
            "lecture_title": ch["title"],
            "student_id": score_data.get("student_id", student_identifier),
            "sanitized_student_id": score_data.get("sanitized_student_id", target_dir.name),
            "original_feedback": claims_data.get("original_feedback", ""),
            "grade": score_data["grade"],
            "total_claims": score_data.get("total_claims", len(claims_list)),
            "claim_statistics": score_data.get("claim_statistics", {}),
            "scores": score_data.get("scores", {}),
            "coverage_details": score_data.get("coverage_details", {}),
            "evaluated_claims": claims_list,
            "files": {
                "claims_json": str(target_dir / "claims.json"),
                "evidence_json": str(target_dir / "evidence.json"),
                "evaluated_json": str(target_dir / "evaluated.json"),
                "score_json": str(target_dir / "score.json"),
            },
        }

    def export_results_report(
        self,
        subject_id: str,
        lecture_id: str,
        fmt: str = "csv",
        student_id: Optional[str] = None,
    ) -> Tuple[bytes, str, str]:
        fmt_lower = fmt.lower().strip()
        if fmt_lower not in ("csv", "json"):
            raise ValueError("Unsupported export format. Choose 'csv' or 'json'.")

        if student_id:
            detail = self.get_student_result_detail(subject_id, lecture_id, student_id)
            safe_sid = detail["sanitized_student_id"]
            if fmt_lower == "json":
                body = json.dumps(detail, indent=2, ensure_ascii=False).encode("utf-8")
                return body, "application/json", f"{subject_id}_{lecture_id}_{safe_sid}_report.json"

            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([
                "course_id", "lecture_id", "student_id", "grade",
                "total_score", "accuracy_score", "coverage_score", "understanding_score",
                "claim_index", "claim_text", "verification_status", "explanation",
                "top_evidence_source", "timestamp_or_page", "similarity_score",
            ])
            scores = detail.get("scores", {})
            for idx, cl in enumerate(detail.get("evaluated_claims", []), start=1):
                top_ev = (cl.get("evidence") or [{}])[0]
                loc = (
                    top_ev.get("timestamp_range")
                    or (f"Page {top_ev['page_number']}" if top_ev.get("page_number") is not None else "")
                )
                writer.writerow([
                    subject_id,
                    lecture_id,
                    detail["student_id"],
                    detail["grade"],
                    scores.get("total", {}).get("score", 0),
                    scores.get("factual_accuracy", {}).get("score", 0),
                    scores.get("lecture_coverage", {}).get("score", 0),
                    scores.get("understanding_quality", {}).get("score", 0),
                    idx,
                    cl.get("claim", ""),
                    cl.get("status", ""),
                    cl.get("explanation", ""),
                    top_ev.get("source_type", ""),
                    loc,
                    top_ev.get("similarity_score", ""),
                ])
            return buf.getvalue().encode("utf-8"), "text/csv", f"{subject_id}_{lecture_id}_{safe_sid}_claims.csv"

        results = self.get_lecture_results(subject_id, lecture_id)
        if fmt_lower == "json":
            body = json.dumps(results, indent=2, ensure_ascii=False).encode("utf-8")
            return body, "application/json", f"{subject_id}_{lecture_id}_evaluation_report.json"

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "course_id",
            "course_name",
            "lecture_id",
            "lecture_title",
            "student_id",
            "grade",
            "total_score_out_of_10",
            "factual_accuracy_out_of_5",
            "lecture_coverage_out_of_3",
            "understanding_out_of_2",
            "total_claims",
            "supported_claims",
            "partially_supported_claims",
            "not_supported_claims",
        ])
        for s in results["students"]:
            writer.writerow([
                results["subject_id"],
                results["subject_name"],
                results["lecture_id"],
                results["lecture_title"],
                s["student_id"],
                s["grade"],
                s["total_score"],
                s["accuracy_score"],
                s["coverage_score"],
                s["understanding_score"],
                s["total_claims"],
                s["supported"],
                s["partially_supported"],
                s["not_supported"],
            ])
        return buf.getvalue().encode("utf-8"), "text/csv", f"{subject_id}_{lecture_id}_evaluation_report.csv"

    # =========================================================================
    # WORKSPACE BACKUP EXPORT & RESTORE (ZIP)
    # =========================================================================

    def export_backup_zip(self, include_knowledge_base: bool = False) -> bytes:
        self.sync_with_filesystem()
        mem = io.BytesIO()
        root = self.data_root

        with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            if self.registry_path.is_file():
                zf.write(self.registry_path, arcname="workspace_registry.json")

            results_root = root / "results"
            if results_root.is_dir():
                for path in sorted(results_root.rglob("*")):
                    if path.is_file():
                        zf.write(path, arcname=str(path.relative_to(root).as_posix()))

            lectures_root = root / "lectures"
            if lectures_root.is_dir():
                for path in sorted(lectures_root.rglob("*")):
                    if not path.is_file():
                        continue
                    rel = path.relative_to(root)
                    parts = rel.parts
                    # Always back up lecture.json, metadata/*, inputs/*; optionally processed/* & knowledge_base/*
                    if path.name == "lecture.json" or "metadata" in parts or "inputs" in parts:
                        zf.write(path, arcname=rel.as_posix())
                    elif include_knowledge_base and ("knowledge_base" in parts or "processed" in parts):
                        zf.write(path, arcname=rel.as_posix())

        return mem.getvalue()

    def restore_backup_zip(self, zip_bytes: bytes) -> Dict[str, Any]:
        if not zip_bytes:
            raise ValueError("Uploaded backup archive is empty.")
        mem = io.BytesIO(zip_bytes)
        if not zipfile.is_zipfile(mem):
            raise ValueError("Uploaded file is not a valid ZIP archive.")

        mem.seek(0)
        restored_files = 0
        root = self.data_root.resolve()

        with self._lock:
            with zipfile.ZipFile(mem, mode="r") as zf:
                members = zf.infolist()
                allowed_top = {"workspace_registry.json", "lectures", "results"}
                for info in members:
                    if info.is_dir():
                        continue
                    rel_posix = info.filename.replace("\\", "/").lstrip("/")
                    if not rel_posix or ".." in Path(rel_posix).parts:
                        raise ValueError(f"Unsafe path inside backup archive: '{info.filename}'")
                    top_part = Path(rel_posix).parts[0]
                    if top_part not in allowed_top:
                        continue
                    dest = (root / rel_posix).resolve()
                    if root not in dest.parents and dest != root:
                        raise ValueError(f"Archive member escapes data root: '{info.filename}'")

                    if rel_posix == "workspace_registry.json" and self.registry_path.is_file():
                        # Merge teachers & subjects rather than wiping existing workspace subjects
                        incoming_reg = json.loads(zf.read(info).decode("utf-8"))
                        current_reg = self._load_raw_registry()
                        existing_tids = {t["teacher_id"] for t in current_reg.get("teachers", [])}
                        for t in incoming_reg.get("teachers", []):
                            if isinstance(t, dict) and t.get("teacher_id") not in existing_tids:
                                current_reg["teachers"].append(t)
                        for sid, sdata in incoming_reg.get("subjects", {}).items():
                            if sid not in current_reg["subjects"]:
                                current_reg["subjects"][sid] = sdata
                            else:
                                for lid, cdata in sdata.get("chapters", {}).items():
                                    if lid not in current_reg["subjects"][sid].get("chapters", {}):
                                        current_reg["subjects"][sid].setdefault("chapters", {})[lid] = cdata
                        self._save_registry(current_reg)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(info, "r") as src_f, open(dest, "wb") as dst_f:
                            shutil.copyfileobj(src_f, dst_f)
                    restored_files += 1

            synced = self.sync_with_filesystem()
            return {
                "status": "restored",
                "restored_files": restored_files,
                "subject_count": len(synced.get("subjects", {})),
            }

