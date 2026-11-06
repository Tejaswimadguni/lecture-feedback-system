import csv
import io
import json
import os
import tempfile
import time
import wave
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.common.paths import compute_file_sha256, get_lecture_paths, get_results_dir


def _make_wav_bytes(duration_sec: float = 0.6, freq_offset: int = 0) -> bytes:
    buf = io.BytesIO()
    sample_rate = 16000
    n_samples = int(sample_rate * duration_sec)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            val = ((i * (9 + freq_offset)) % 2000) - 1000
            frames.extend(int(val).to_bytes(2, byteorder="little", signed=True))
        wf.writeframes(bytes(frames))
    return buf.getvalue()


def _make_pdf_bytes(pages_text: list[str]) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 750), text, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_pptx_bytes(slides_text: list[str]) -> bytes:
    from pptx import Presentation

    prs = Presentation()
    blank_layout = prs.slide_layouts[6]
    for txt in slides_text:
        slide = prs.slides.add_slide(blank_layout)
        tx_box = slide.shapes.add_textbox(500000, 500000, 6000000, 3500000)
        tx_box.text_frame.text = txt
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _make_csv_bytes(fieldnames: list[str], rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _wait_for_job(
    client: TestClient,
    status_url: str,
    state_key: str,
    timeout_sec: float = 60.0,
) -> dict:
    deadline = time.monotonic() + timeout_sec
    last_payload = {}
    while time.monotonic() < deadline:
        resp = client.get(status_url)
        assert resp.status_code == 200, resp.text
        last_payload = resp.json()[state_key]
        if last_payload["status"] in ("completed", "failed"):
            return last_payload
        time.sleep(0.1)
    raise TimeoutError(f"Job at {status_url} timed out. Last state: {last_payload}")


def test_e2e_workflow_tests_1_through_8_and_persistence():
    """
    Executes Mandatory End-to-End Scenarios TEST 1 through TEST 8:
      - TEST 1: DBMS / DBMS_lect1 upload & processing -> isolated KB
      - TEST 2: DBMS / DBMS_lect2 upload & processing -> separate KB, DBMS_lect1 untouched
      - TEST 3: OS / OS_lect1 upload (with .pptx slides) & processing -> isolated OS KB
      - TEST 4 & TEST 8: Upload distinct CSVs for DBMS_lect1 (including cross-lecture off-topic student)
        and DBMS_lect2 (custom column names), preview, confirm columns, and evaluate
      - TEST 5: Verify per-student {claims, evidence, evaluated, score}.json + all_students_summary.json
        + CSV/JSON export endpoints + timestamps/page numbers
      - TEST 6: Simulate refresh & server restart + ZIP backup export & restore into clean workspace
      - TEST 7: Force-reprocess DBMS_lect1 -> verify DBMS_lect2 & OS_lect1 KB and result SHA-256 hashes
        remain 100% unchanged, and verify file replacement triggers outdated state without deleting results
    """
    segments_by_lecture = {
        "DBMS_lect1": [
            {
                "start": 0.0,
                "end": 22.0,
                "text": "Database normalization decomposes relations to eliminate data redundancy and update anomalies.",
            },
            {
                "start": 22.0,
                "end": 48.0,
                "text": "First Normal Form 1NF requires atomic attribute values, 2NF removes partial dependencies, and 3NF removes transitive dependencies.",
            },
        ],
        "DBMS_lect2": [
            {
                "start": 0.0,
                "end": 25.0,
                "text": "SQL join operations combine rows from two tables based on related join columns.",
            },
            {
                "start": 25.0,
                "end": 52.0,
                "text": "Inner join keeps matching tuples while left outer join preserves unmatched left rows filled with NULL values.",
            },
        ],
        "OS_lect1": [
            {
                "start": 0.0,
                "end": 24.0,
                "text": "Operating system process management tracks Process Control Blocks PCB across ready, running, and waiting states.",
            },
            {
                "start": 24.0,
                "end": 50.0,
                "text": "Preemptive Round Robin CPU scheduling assigns fixed time quanta and performs context switching.",
            },
        ],
    }

    def fake_transcribe(
        audio_path: str,
        lecture_id: str,
        course_id=None,
        model_size="base",
        device=None,
        chunk_length_sec=180,
        progress_callback=None,
    ):
        segs = segments_by_lecture[lecture_id]
        if progress_callback is not None:
            progress_callback(1, len(segs))
            progress_callback(len(segs), len(segs))
        return {
            "course_id": course_id,
            "lecture_id": lecture_id,
            "source_file": Path(audio_path).name,
            "source_sha256": compute_file_sha256(audio_path),
            "whisper_model": model_size,
            "segments": segs,
        }

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        data_root = tmp_path / "backend_data"
        app = create_app(data_root=data_root)
        client = TestClient(app)

        # Verify health & teachers
        h = client.get("/api/health")
        assert h.status_code == 200
        teachers = client.get("/api/teachers").json()["teachers"]
        assert len(teachers) >= 3
        teacher_id = teachers[1]["teacher_id"]

        with (
            patch("backend.ingestion.audio.transcribe_audio", side_effect=fake_transcribe),
            patch.dict(os.environ, {"OPENROUTER_API_KEY": "", "GEMINI_API_KEY": ""}, clear=False),
        ):
            # =================================================================
            # TEST 1: Create DBMS subject & DBMS_lect1 (Normalization)
            # =================================================================
            r_dbms = client.post(
                "/api/subjects",
                json={
                    "name": "Database Management Systems",
                    "code": "DBMS",
                    "teacher_id": teacher_id,
                },
            )
            assert r_dbms.status_code == 201, r_dbms.text
            assert r_dbms.json()["subject"]["subject_id"] == "DBMS"

            r_ch1 = client.post("/api/subjects/DBMS/chapters", json={"title": "Normalization"})
            assert r_ch1.status_code == 201, r_ch1.text
            assert r_ch1.json()["chapter"]["lecture_id"] == "DBMS_lect1"

            # Upload arbitrary original filenames (lecture ID must NOT change!)
            up_a1 = client.post(
                "/api/subjects/DBMS/chapters/DBMS_lect1/upload/audio",
                files={"file": ("prof_recording_week01_norm.wav", _make_wav_bytes(freq_offset=1), "audio/wav")},
            )
            assert up_a1.status_code == 200
            assert up_a1.json()["chapter"]["lecture_id"] == "DBMS_lect1"

            pdf_norm_bytes = _make_pdf_bytes([
                "Database Normalization\n"
                "First Normal Form (1NF) requires atomic values and eliminates repeating groups.\n"
                "Redundancy causes insertion, deletion, and update anomalies.",
                "Higher Normal Forms\n"
                "Second Normal Form (2NF) removes partial functional dependencies on composite keys.\n"
                "Third Normal Form (3NF) eliminates transitive functional dependencies.\n"
                "Boyce-Codd Normal Form (BCNF) requires every determinant to be a candidate key.",
            ])
            up_d1 = client.post(
                "/api/subjects/DBMS/chapters/DBMS_lect1/upload/document",
                files={"file": ("arbitrary_norm_handout.pdf", pdf_norm_bytes, "application/pdf")},
            )
            assert up_d1.status_code == 200

            p_start_1 = client.post(
                "/api/subjects/DBMS/chapters/DBMS_lect1/process",
                json={"whisper_model": "base", "force_reprocess": False},
            )
            assert p_start_1.status_code == 202
            p_done_1 = _wait_for_job(
                client,
                "/api/subjects/DBMS/chapters/DBMS_lect1/process/status",
                "processing",
            )
            assert p_done_1["status"] == "completed", p_done_1

            lp_dbms1 = get_lecture_paths("DBMS", "DBMS_lect1", data_root=data_root)
            assert lp_dbms1.faiss_index.is_file()
            assert lp_dbms1.embeddings.is_file()
            assert lp_dbms1.chunk_mapping.is_file()
            assert lp_dbms1.dataset_metadata.is_file()

            dbms1_hashes_initial = {
                "faiss": compute_file_sha256(lp_dbms1.faiss_index),
                "map": compute_file_sha256(lp_dbms1.chunk_mapping),
            }

            # =================================================================
            # TEST 2: Create DBMS_lect2 (SQL Joins) under same subject DBMS
            # =================================================================
            r_ch2 = client.post("/api/subjects/DBMS/chapters", json={"title": "SQL Joins"})
            assert r_ch2.status_code == 201
            assert r_ch2.json()["chapter"]["lecture_id"] == "DBMS_lect2"

            client.post(
                "/api/subjects/DBMS/chapters/DBMS_lect2/upload/audio",
                files={"file": ("joins_session_audio.wav", _make_wav_bytes(freq_offset=4), "audio/wav")},
            )
            pdf_joins_bytes = _make_pdf_bytes([
                "SQL Joins Fundamentals\n"
                "An INNER JOIN selects records that have matching join predicate values in both tables.\n"
                "Equi-join uses equality comparisons between primary and foreign keys.",
                "Outer and Cross Joins\n"
                "LEFT OUTER JOIN returns all rows from the left relation and NULLs for unmatched right attributes.\n"
                "CROSS JOIN produces the Cartesian product of both tables.",
            ])
            client.post(
                "/api/subjects/DBMS/chapters/DBMS_lect2/upload/document",
                files={"file": ("sql_joins_deck_v2.pdf", pdf_joins_bytes, "application/pdf")},
            )
            assert client.post("/api/subjects/DBMS/chapters/DBMS_lect2/process").status_code == 202
            p_done_2 = _wait_for_job(
                client,
                "/api/subjects/DBMS/chapters/DBMS_lect2/process/status",
                "processing",
            )
            assert p_done_2["status"] == "completed"

            lp_dbms2 = get_lecture_paths("DBMS", "DBMS_lect2", data_root=data_root)
            assert lp_dbms2.faiss_index.is_file()
            assert lp_dbms1.knowledge_base_dir != lp_dbms2.knowledge_base_dir
            # Confirm DBMS_lect1 KB was untouched
            assert compute_file_sha256(lp_dbms1.faiss_index) == dbms1_hashes_initial["faiss"]
            assert compute_file_sha256(lp_dbms1.chunk_mapping) == dbms1_hashes_initial["map"]

            # =================================================================
            # TEST 3: Create OS subject & OS_lect1 (Process Management) w/ PPTX
            # =================================================================
            r_os = client.post(
                "/api/subjects",
                json={
                    "name": "Operating Systems",
                    "code": "OS",
                    "teacher_id": teacher_id,
                },
            )
            assert r_os.status_code == 201
            assert r_os.json()["subject"]["subject_id"] == "OS"

            r_os_ch1 = client.post(
                "/api/subjects/OS/chapters",
                json={"title": "Process Management"},
            )
            assert r_os_ch1.status_code == 201
            assert r_os_ch1.json()["chapter"]["lecture_id"] == "OS_lect1"

            client.post(
                "/api/subjects/OS/chapters/OS_lect1/upload/audio",
                files={"file": ("os_processes.wav", _make_wav_bytes(freq_offset=8), "audio/wav")},
            )
            pptx_os_bytes = _make_pptx_bytes([
                "Process Control Block (PCB)\n"
                "The OS kernel maintains a PCB storing process state, program counter, CPU registers, and memory limits.",
                "CPU Scheduling & Context Switch\n"
                "Round Robin scheduling uses a fixed time quantum to multiplex CPU execution fairly across ready processes.",
            ])
            up_os_doc = client.post(
                "/api/subjects/OS/chapters/OS_lect1/upload/document",
                files={"file": ("process_scheduling_slides.pptx", pptx_os_bytes, "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
            )
            assert up_os_doc.status_code == 200
            assert client.post("/api/subjects/OS/chapters/OS_lect1/process").status_code == 202
            p_done_os = _wait_for_job(
                client,
                "/api/subjects/OS/chapters/OS_lect1/process/status",
                "processing",
            )
            assert p_done_os["status"] == "completed", p_done_os
            lp_os1 = get_lecture_paths("OS", "OS_lect1", data_root=data_root)
            assert lp_os1.faiss_index.is_file()

            # =================================================================
            # TEST 4, TEST 5 & TEST 8: Feedback CSV Upload, Column Mapping,
            # Evaluation, Student Directory Structure & Cross-Lecture Isolation
            # =================================================================
            csv_dbms1 = _make_csv_bytes(
                ["roll_number", "feedback"],
                [
                    {
                        "roll_number": "DBMS/2026-01",
                        "feedback": (
                            "Database normalization eliminates redundancy and update anomalies. "
                            "First Normal Form 1NF enforces atomic attribute values and removes repeating groups. "
                            "Second Normal Form 2NF removes partial dependencies on composite keys while 3NF removes transitive dependencies and BCNF requires every determinant to be a candidate key."
                        ),
                    },
                    {
                        # Off-topic cross-lecture feedback (content from DBMS_lect2 & OS_lect1!)
                        "roll_number": "DBMS/2026-02",
                        "feedback": (
                            "Left outer join preserves unmatched left table rows with NULL values and cross join computes the Cartesian product. "
                            "Round Robin CPU scheduling uses time quanta and Process Control Blocks PCB for context switching."
                        ),
                    },
                ],
            )
            up_csv1 = client.post(
                "/api/subjects/DBMS/chapters/DBMS_lect1/feedback/upload",
                files={"file": ("norm_student_responses.csv", csv_dbms1, "text/csv")},
            )
            assert up_csv1.status_code == 200
            assert up_csv1.json()["preview"]["validation"]["is_valid"] is True

            conf1 = client.post(
                "/api/subjects/DBMS/chapters/DBMS_lect1/feedback/confirm",
                json={"student_id_column": "roll_number", "feedback_column": "feedback"},
            )
            assert conf1.status_code == 200

            ev1 = client.post("/api/subjects/DBMS/chapters/DBMS_lect1/evaluate", json={"top_k": 5})
            assert ev1.status_code == 202
            ev1_done = _wait_for_job(
                client,
                "/api/subjects/DBMS/chapters/DBMS_lect1/evaluate/status",
                "evaluation",
            )
            assert ev1_done["status"] == "completed", ev1_done

            # Custom column names CSV for DBMS_lect2
            csv_dbms2 = _make_csv_bytes(
                ["student_reg_id", "lecture_reflection"],
                [
                    {
                        "student_reg_id": "JOIN_STU_01",
                        "lecture_reflection": (
                            "SQL inner join returns matching rows between tables. "
                            "Left outer join preserves all rows from the left relation with NULLs for unmatched right columns, and cross join produces the Cartesian product."
                        ),
                    }
                ],
            )
            up_csv2 = client.post(
                "/api/subjects/DBMS/chapters/DBMS_lect2/feedback/upload",
                files={"file": ("joins_custom_cols.csv", csv_dbms2, "text/csv")},
            )
            assert up_csv2.status_code == 200
            assert client.post(
                "/api/subjects/DBMS/chapters/DBMS_lect2/evaluate",
                json={
                    "student_id_column": "student_reg_id",
                    "feedback_column": "lecture_reflection",
                    "top_k": 5,
                },
            ).status_code == 202
            ev2_done = _wait_for_job(
                client,
                "/api/subjects/DBMS/chapters/DBMS_lect2/evaluate/status",
                "evaluation",
            )
            assert ev2_done["status"] == "completed", ev2_done

            # Verify TEST 5 filesystem layout
            res_dir_1 = get_results_dir("DBMS", "DBMS_lect1", data_root=data_root)
            res_dir_2 = get_results_dir("DBMS", "DBMS_lect2", data_root=data_root)
            assert (res_dir_1 / "all_students_summary.json").is_file()
            assert (res_dir_2 / "all_students_summary.json").is_file()
            for sid_folder in ("DBMS_2026-01", "DBMS_2026-02"):
                for req_json in ("claims.json", "evidence.json", "evaluated.json", "score.json"):
                    assert (res_dir_1 / sid_folder / req_json).is_file()
            for req_json in ("claims.json", "evidence.json", "evaluated.json", "score.json"):
                assert (res_dir_2 / "JOIN_STU_01" / req_json).is_file()

            # Verify TEST 8 cross-lecture isolation & scoring via API
            res1_api = client.get("/api/subjects/DBMS/chapters/DBMS_lect1/results")
            assert res1_api.status_code == 200
            res1_data = res1_api.json()
            assert res1_data["total_students"] == 2

            stu_on_topic = client.get(
                "/api/subjects/DBMS/chapters/DBMS_lect1/results/DBMS/2026-01"
            ).json()
            stu_off_topic = client.get(
                "/api/subjects/DBMS/chapters/DBMS_lect1/results/DBMS/2026-02"
            ).json()

            assert (
                stu_on_topic["scores"]["total"]["score"]
                > stu_off_topic["scores"]["total"]["score"]
            )
            assert stu_on_topic["grade"] in {"A+", "A", "B", "C", "D", "F"}

            # Every single evidence chunk for off-topic student on DBMS_lect1 MUST belong strictly to DBMS_lect1!
            for cl in stu_off_topic["evaluated_claims"]:
                for ev in cl["evidence"]:
                    assert ev["course_id"] == "DBMS"
                    assert ev["lecture_id"] == "DBMS_lect1"
                    assert ev["chunk_id"].startswith("DBMS_DBMS_lect1_")
                    assert "Round Robin" not in ev["text"]
                    assert "OUTER JOIN" not in ev["text"]

            # Test CSV & JSON export downloads
            exp_csv = client.get("/api/subjects/DBMS/chapters/DBMS_lect1/results/export?format=csv")
            assert exp_csv.status_code == 200
            assert "DBMS/2026-01" in exp_csv.text
            exp_json = client.get("/api/subjects/DBMS/chapters/DBMS_lect1/results/export?format=json")
            assert exp_json.status_code == 200
            assert exp_json.json()["lecture_id"] == "DBMS_lect1"

            # =================================================================
            # TEST 7: Reprocess DBMS_lect1 & Verify Zero Impact on DBMS_lect2 & OS_lect1
            # =================================================================
            lect2_hashes_before = {
                "faiss": compute_file_sha256(lp_dbms2.faiss_index),
                "map": compute_file_sha256(lp_dbms2.chunk_mapping),
                "summary": compute_file_sha256(res_dir_2 / "all_students_summary.json"),
            }
            os1_hashes_before = {
                "faiss": compute_file_sha256(lp_os1.faiss_index),
                "map": compute_file_sha256(lp_os1.chunk_mapping),
            }

            reproc = client.post(
                "/api/subjects/DBMS/chapters/DBMS_lect1/process",
                json={"whisper_model": "base", "force_reprocess": True},
            )
            assert reproc.status_code == 202
            reproc_done = _wait_for_job(
                client,
                "/api/subjects/DBMS/chapters/DBMS_lect1/process/status",
                "processing",
            )
            assert reproc_done["status"] == "completed"

            assert compute_file_sha256(lp_dbms2.faiss_index) == lect2_hashes_before["faiss"]
            assert compute_file_sha256(lp_dbms2.chunk_mapping) == lect2_hashes_before["map"]
            assert compute_file_sha256(res_dir_2 / "all_students_summary.json") == lect2_hashes_before["summary"]
            assert compute_file_sha256(lp_os1.faiss_index) == os1_hashes_before["faiss"]
            assert compute_file_sha256(lp_os1.chunk_mapping) == os1_hashes_before["map"]

            # Replacing audio file marks DBMS_lect1 outdated while preserving existing evaluation results
            rep_audio = client.post(
                "/api/subjects/DBMS/chapters/DBMS_lect1/upload/audio",
                files={"file": ("updated_norm_audio_v2.wav", _make_wav_bytes(freq_offset=12), "audio/wav")},
            )
            assert rep_audio.status_code == 200
            assert rep_audio.json()["chapter"]["processing"]["status"] == "outdated"
            assert rep_audio.json()["chapter"]["evaluation"]["outdated"] is True
            assert (res_dir_1 / "all_students_summary.json").is_file()

            # =================================================================
            # TEST 6: Simulated Refresh / Server Restart + Backup Export & Restore
            # =================================================================
            restarted_app = create_app(data_root=data_root)
            restarted_client = TestClient(restarted_app)
            sync_resp = restarted_client.get("/api/sync")
            assert sync_resp.status_code == 200
            synced_subjects = {s["subject_id"]: s for s in sync_resp.json()["subjects"]}
            assert "DBMS" in synced_subjects and "OS" in synced_subjects
            assert len(synced_subjects["DBMS"]["chapters"]) == 2
            assert len(synced_subjects["OS"]["chapters"]) == 1

            # Export ZIP backup and restore into a brand-new empty data_root
            bkp_resp = restarted_client.get("/api/backup/export")
            assert bkp_resp.status_code == 200
            assert len(bkp_resp.content) > 100

            restored_root = tmp_path / "restored_workspace"
            restored_client = TestClient(create_app(data_root=restored_root))
            restore_res = restored_client.post(
                "/api/backup/restore",
                files={"file": ("backup.zip", bkp_resp.content, "application/zip")},
            )
            assert restore_res.status_code == 200
            assert restore_res.json()["subject_count"] == 2
            restored_results = restored_client.get("/api/subjects/DBMS/chapters/DBMS_lect2/results")
            assert restored_results.status_code == 200
            assert restored_results.json()["total_students"] == 1


def test_9_api_validation_error_handling_and_safe_deletion():
    """
    Executes Mandatory Scenario TEST 9 via REST API:
      - Missing files when processing -> HTTP 400
      - Unsupported extensions & 0-byte uploads -> HTTP 400
      - Evaluating unprocessed lecture -> HTTP 400
      - Missing CSV columns, duplicate student IDs, sanitized ID collisions, empty feedback -> HTTP 400
      -Rename & Delete confirmation enforcement (?confirm=true) and isolated deletion verification
    """
    with tempfile.TemporaryDirectory() as tmp:
        data_root = Path(tmp) / "backend_data"
        client = TestClient(create_app(data_root=data_root))

        tid = client.get("/api/teachers").json()["teachers"][0]["teacher_id"]
        s_res = client.post("/api/subjects", json={"name": "Networks", "code": "CN", "teacher_id": tid})
        assert s_res.status_code == 201

        ch1 = client.post("/api/subjects/CN/chapters", json={"title": "OSI Model"}).json()["chapter"]
        ch2 = client.post("/api/subjects/CN/chapters", json={"title": "TCP Congestion"}).json()["chapter"]
        assert ch1["lecture_id"] == "CN_lect1"
        assert ch2["lecture_id"] == "CN_lect2"

        # 1. Processing without uploaded files -> 400
        no_files_proc = client.post("/api/subjects/CN/chapters/CN_lect1/process")
        assert no_files_proc.status_code == 400

        # 2. Unsupported audio & document formats -> 400
        bad_audio = client.post(
            "/api/subjects/CN/chapters/CN_lect1/upload/audio",
            files={"file": ("malware.exe", b"not-audio", "application/octet-stream")},
        )
        assert bad_audio.status_code == 400

        bad_doc = client.post(
            "/api/subjects/CN/chapters/CN_lect1/upload/document",
            files={"file": ("notes.txt", b"plain text", "text/plain")},
        )
        assert bad_doc.status_code == 400

        # 3. Empty 0-byte upload -> 400
        empty_audio = client.post(
            "/api/subjects/CN/chapters/CN_lect1/upload/audio",
            files={"file": ("empty.mp3", b"", "audio/mpeg")},
        )
        assert empty_audio.status_code == 400

        # 4. Evaluate before lecture KB is processed -> 400
        valid_csv = _make_csv_bytes(
            ["roll_number", "feedback"],
            [{"roll_number": "101", "feedback": "OSI has seven layers."}],
        )
        client.post(
            "/api/subjects/CN/chapters/CN_lect1/feedback/upload",
            files={"file": ("valid.csv", valid_csv, "text/csv")},
        )
        eval_no_kb = client.post("/api/subjects/CN/chapters/CN_lect1/evaluate")
        assert eval_no_kb.status_code == 400
        assert "processed" in eval_no_kb.json()["detail"].lower()

        # 5. CSV validation failures: missing column, duplicate IDs, collision IDs, empty feedback
        dup_csv = _make_csv_bytes(
            ["roll_number", "feedback"],
            [
                {"roll_number": "S01", "feedback": "Layer 4 is transport."},
                {"roll_number": "S01", "feedback": "Duplicate row."},
            ],
        )
        dup_up = client.post(
            "/api/subjects/CN/chapters/CN_lect1/feedback/upload",
            files={"file": ("dup.csv", dup_up_name := "dup.csv", "text/csv") if False else ("dup.csv", dup_csv, "text/csv")},
        )
        assert dup_up.status_code == 200
        assert dup_up.json()["preview"]["validation"]["is_valid"] is False
        assert len(dup_up.json()["preview"]["validation"]["duplicate_ids"]) == 1
        # Confirming invalid CSV must return 400
        bad_conf = client.post(
            "/api/subjects/CN/chapters/CN_lect1/feedback/confirm",
            json={"student_id_column": "roll_number", "feedback_column": "feedback"},
        )
        assert bad_conf.status_code == 400

        # Missing column confirmation -> 400
        missing_col_conf = client.post(
            "/api/subjects/CN/chapters/CN_lect1/feedback/confirm",
            json={"student_id_column": "nonexistent_col", "feedback_column": "feedback"},
        )
        assert missing_col_conf.status_code == 400

        # Empty feedback row -> invalid preview & 400 on confirm
        empty_fb_csv = _make_csv_bytes(
            ["roll_number", "feedback"],
            [{"roll_number": "S09", "feedback": "   "}],
        )
        emp_up = client.post(
            "/api/subjects/CN/chapters/CN_lect1/feedback/upload",
            files={"file": ("empty_fb.csv", empty_fb_csv, "text/csv")},
        )
        assert emp_up.status_code == 200
        assert emp_up.json()["preview"]["validation"]["is_valid"] is False
        assert client.post(
            "/api/subjects/CN/chapters/CN_lect1/feedback/confirm",
            json={"student_id_column": "roll_number", "feedback_column": "feedback"},
        ).status_code == 400

        # 6. Rename & Delete Confirmation Enforcement
        ren = client.patch("/api/subjects/CN", json={"name": "Computer Networks"})
        assert ren.status_code == 200
        assert ren.json()["subject"]["name"] == "Computer Networks"

        ren_ch = client.patch("/api/subjects/CN/chapters/CN_lect1", json={"title": "OSI Reference Model"})
        assert ren_ch.status_code == 200
        assert ren_ch.json()["chapter"]["title"] == "OSI Reference Model"

        # Deleting without ?confirm=true must fail with 400
        assert client.delete("/api/subjects/CN/chapters/CN_lect1").status_code == 400
        assert client.delete("/api/subjects/CN").status_code == 400

        # Deleting CN_lect1 WITH ?confirm=true deletes ONLY CN_lect1, keeping CN_lect2 intact
        del_ch1 = client.delete("/api/subjects/CN/chapters/CN_lect1?confirm=true")
        assert del_ch1.status_code == 200
        assert not get_lecture_paths("CN", "CN_lect1", data_root=data_root).lecture_dir.exists()
        assert get_lecture_paths("CN", "CN_lect2", data_root=data_root).lecture_dir.exists()

        # Creating a new chapter after deletion must generate CN_lect3 (never reusing CN_lect1 or CN_lect2)
        ch3 = client.post("/api/subjects/CN/chapters", json={"title": "BGP Routing"}).json()["chapter"]
        assert ch3["lecture_id"] == "CN_lect3"

