import csv
import json
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.paths import compute_file_sha256, get_lecture_paths, get_results_dir
from backend.retrival.search import search
from backend.retrival.vector_store import validate_and_load_knowledge_base
from backend.run_lecture_pipeline import run_pipeline
from backend.verification.claims import load_and_validate_feedback_csv
from backend.verification.llm_client import LLMAPIError, call_llm_json, redact_secrets
from backend.verification.pipeline import run_verification_pipeline


def _create_dummy_wav(file_path: Path, duration_sec: float = 1.0, freq_offset: int = 0) -> Path:
    """Creates a valid non-empty PCM WAV audio file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 16000
    n_samples = int(sample_rate * duration_sec)
    with wave.open(str(file_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            val = ((i * (7 + freq_offset)) % 2000) - 1000
            frames.extend(int(val).to_bytes(2, byteorder="little", signed=True))
        wf.writeframes(bytes(frames))
    return file_path


def _create_pdf(file_path: Path, pages_text: list[str]) -> Path:
    """Creates a real multi-page PDF document using PyMuPDF."""
    import pymupdf

    file_path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 750), text, fontsize=11)
    doc.save(str(file_path))
    doc.close()
    return file_path


def _write_csv(file_path: Path, fieldnames: list[str], rows: list[dict]) -> Path:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return file_path


def _ingest_two_dbms_lectures(data_root: Path, work_dir: Path):
    """Helper to ingest DBMS_lect1 (Normalization) and DBMS_lect2 (SQL Joins) with mocked Whisper."""
    audio_1 = _create_dummy_wav(work_dir / "inputs" / "any_audio_norm.wav", freq_offset=1)
    pdf_1 = _create_pdf(
        work_dir / "inputs" / "arbitrary_norm_slides.pdf",
        [
            "Database Normalization Overview\n"
            "First Normal Form (1NF) requires atomic attribute values and removes repeating groups.\n"
            "Update, insertion, and deletion anomalies arise from redundant data storage.",
            "Second and Third Normal Forms\n"
            "Second Normal Form (2NF) eliminates partial functional dependencies on composite primary keys.\n"
            "Third Normal Form (3NF) removes transitive functional dependencies between non-key attributes.\n"
            "Boyce-Codd Normal Form (BCNF) requires every determinant to be a candidate key.",
        ],
    )

    audio_2 = _create_dummy_wav(work_dir / "inputs" / "different_joins_audio.wav", freq_offset=5)
    pdf_2 = _create_pdf(
        work_dir / "inputs" / "custom_sql_joins_deck.pdf",
        [
            "SQL Join Operations\n"
            "An INNER JOIN returns only rows that have matching join predicate values in both tables.\n"
            "Equi-joins compare foreign key and primary key columns using equality.",
            "Outer Joins and Cross Joins\n"
            "A LEFT OUTER JOIN preserves all rows from the left table and fills unmatched right columns with NULL.\n"
            "A RIGHT OUTER JOIN preserves all rows from the right table.\n"
            "A CROSS JOIN produces the Cartesian product of all rows from both relations.",
        ],
    )

    lect1_segments = [
        {
            "start": 0.0,
            "end": 18.0,
            "text": "Database normalization organizes relational schemas to eliminate redundancy and update anomalies.",
        },
        {
            "start": 18.0,
            "end": 40.0,
            "text": "First Normal Form 1NF enforces atomic attribute domains, while 2NF and 3NF remove partial and transitive dependencies.",
        },
    ]

    lect2_segments = [
        {
            "start": 0.0,
            "end": 20.0,
            "text": "SQL joins combine tuples from two or more relational tables based on a join condition.",
        },
        {
            "start": 20.0,
            "end": 45.0,
            "text": "Inner join returns matching rows only, whereas left outer join keeps unmatched left rows padded with NULL values.",
        },
    ]

    def fake_transcribe(audio_path: str, lecture_id: str, course_id=None, model_size="base", device=None, chunk_length_sec=180):
        segs = lect1_segments if lecture_id == "DBMS_lect1" else lect2_segments
        return {
            "course_id": course_id,
            "lecture_id": lecture_id,
            "source_file": Path(audio_path).name,
            "source_sha256": compute_file_sha256(audio_path),
            "whisper_model": model_size,
            "segments": segs,
        }

    with patch("backend.ingestion.audio.transcribe_audio", side_effect=fake_transcribe):
        res1 = run_pipeline(
            course_id="DBMS",
            lecture_id="DBMS_lect1",
            course_name="Database Management Systems",
            lecture_title="Normalization",
            audio_path=audio_1,
            pdf_path=pdf_1,
            data_root=data_root,
        )
        kb1_hashes_before_lect2 = {
            "faiss": compute_file_sha256(res1["faiss_index_path"]),
            "emb": compute_file_sha256(res1["embeddings_path"]),
            "map": compute_file_sha256(res1["chunk_mapping_path"]),
            "meta": compute_file_sha256(res1["dataset_metadata_path"]),
        }

        res2 = run_pipeline(
            course_id="DBMS",
            lecture_id="DBMS_lect2",
            course_name="Database Management Systems",
            lecture_title="SQL Joins",
            audio_path=audio_2,
            pdf_path=pdf_2,
            data_root=data_root,
        )

    return res1, res2, kb1_hashes_before_lect2, (audio_1, pdf_1, audio_2, pdf_2), fake_transcribe


def test_1_2_3_4_separate_directories_kbs_and_reprocessing_isolation():
    """
    Tests Mandatory Requirements 1, 2, 3, and 4:
      1. Two lectures in the same subject create separate directories.
      2. Each lecture gets its own raw/, processed/, metadata/, and knowledge_base/ files.
      3. Ingesting Lecture 2 does not alter Lecture 1's knowledge base.
      4. Reprocessing Lecture 1 replaces Lecture 1's KB cleanly without duplicating chunks
         and does not alter Lecture 2's knowledge base.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        data_root = tmp_path / "backend_data"

        res1, res2, kb1_hashes_before_lect2, inputs, fake_transcribe = _ingest_two_dbms_lectures(
            data_root, tmp_path
        )
        audio_1, pdf_1, _, _ = inputs

        p1 = get_lecture_paths("DBMS", "DBMS_lect1", data_root=data_root)
        p2 = get_lecture_paths("DBMS", "DBMS_lect2", data_root=data_root)

        # 1. Separate directories under lectures/DBMS/{lecture_id}
        assert p1.lecture_dir != p2.lecture_dir
        assert p1.lecture_dir.exists() and p2.lecture_dir.exists()

        # 2. Complete independent set of required files for both lectures
        for lp in (p1, p2):
            assert lp.raw_dir.exists()
            assert len(list(lp.raw_dir.iterdir())) == 2
            assert lp.transcript_raw.exists()
            assert lp.transcript_clean.exists()
            assert lp.transcript_chunks.exists()
            assert lp.pdf_raw.exists()
            assert lp.pdf_clean.exists()
            assert lp.pdf_chunks.exists()
            assert lp.dataset_metadata.exists()
            assert lp.faiss_index.exists()
            assert lp.embeddings.exists()
            assert lp.chunk_mapping.exists()

        # Verify no global index or legacy lecture_01 files were created
        assert not (data_root / "vector_store").exists()
        assert not (p1.processed_dir / "lecture_01_raw.json").exists()
        assert not (p1.processed_dir / "lecture_01_chunks.json").exists()

        # 3. Ingesting Lecture 2 did NOT modify Lecture 1's KB or metadata byte-for-byte
        assert compute_file_sha256(p1.faiss_index) == kb1_hashes_before_lect2["faiss"]
        assert compute_file_sha256(p1.embeddings) == kb1_hashes_before_lect2["emb"]
        assert compute_file_sha256(p1.chunk_mapping) == kb1_hashes_before_lect2["map"]
        assert compute_file_sha256(p1.dataset_metadata) == kb1_hashes_before_lect2["meta"]

        # 4. Snapshot Lecture 2 hashes, then reprocess Lecture 1 (--force-reprocess)
        kb2_hashes_before_reprocess = {
            "faiss": compute_file_sha256(p2.faiss_index),
            "emb": compute_file_sha256(p2.embeddings),
            "map": compute_file_sha256(p2.chunk_mapping),
            "meta": compute_file_sha256(p2.dataset_metadata),
        }
        original_lect1_count = res1["total_index_chunks"]

        with patch("backend.ingestion.audio.transcribe_audio", side_effect=fake_transcribe):
            res1_reprocessed = run_pipeline(
                course_id="DBMS",
                lecture_id="DBMS_lect1",
                course_name="Database Management Systems",
                lecture_title="Normalization",
                audio_path=audio_1,
                pdf_path=pdf_1,
                force_reprocess=True,
                data_root=data_root,
            )

        # Lecture 1 chunk count must remain identical (replaced, never duplicated)
        assert res1_reprocessed["total_index_chunks"] == original_lect1_count
        # Lecture 2 KB must remain 100% untouched byte-for-byte
        assert compute_file_sha256(p2.faiss_index) == kb2_hashes_before_reprocess["faiss"]
        assert compute_file_sha256(p2.embeddings) == kb2_hashes_before_reprocess["emb"]
        assert compute_file_sha256(p2.chunk_mapping) == kb2_hashes_before_reprocess["map"]
        assert compute_file_sha256(p2.dataset_metadata) == kb2_hashes_before_reprocess["meta"]


def test_5_6_strict_retrieval_cross_lecture_isolation():
    """
    Tests Mandatory Requirements 5 and 6:
      5. Retrieval from Lecture 1 cannot return Lecture 2 evidence.
      6. Retrieval from Lecture 2 cannot return Lecture 1 evidence.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        data_root = tmp_path / "backend_data"
        _ingest_two_dbms_lectures(data_root, tmp_path)

        # Query Lecture 1 even with Lecture 2 terminology ("LEFT OUTER JOIN Cartesian product")
        hits_from_lect1 = search(
            query="LEFT OUTER JOIN preserves left rows and CROSS JOIN Cartesian product",
            course_id="DBMS",
            lecture_id="DBMS_lect1",
            top_k=10,
            data_root=data_root,
        )
        assert len(hits_from_lect1) > 0
        for h in hits_from_lect1:
            assert h["course_id"] == "DBMS"
            assert h["lecture_id"] == "DBMS_lect1"
            assert h["chunk_id"].startswith("DBMS_DBMS_lect1_")
            assert "OUTER JOIN" not in h["text"]

        # Query Lecture 2 even with Lecture 1 terminology ("Boyce-Codd Normal Form transitive dependency")
        hits_from_lect2 = search(
            query="Boyce-Codd Normal Form BCNF and 3NF transitive functional dependencies",
            course_id="DBMS",
            lecture_id="DBMS_lect2",
            top_k=10,
            data_root=data_root,
        )
        assert len(hits_from_lect2) > 0
        for h in hits_from_lect2:
            assert h["course_id"] == "DBMS"
            assert h["lecture_id"] == "DBMS_lect2"
            assert h["chunk_id"].startswith("DBMS_DBMS_lect2_")
            assert "Boyce-Codd" not in h["text"]


def test_7_8_11_dynamic_verification_student_directories_custom_csv_and_scoring():
    """
    Tests Mandatory Requirements 7, 8, and 11:
      7. Each student gets a separate sanitized results directory with claims, evidence, evaluated, score,
         plus all_students_summary.json.
      8. Different CSV filenames, arbitrary locations, and custom column names work.
      11. End-to-end ingestion + verification runs cleanly for both lectures, with dynamic lecture-specific
          coverage scoring (no cross-lecture credit).
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        data_root = tmp_path / "backend_data"
        _ingest_two_dbms_lectures(data_root, tmp_path)

        # CSV 1 in custom directory with default columns
        csv_lect1 = _write_csv(
            tmp_path / "custom_csv_folder_A" / "dbms_normalization_reflections.csv",
            fieldnames=["roll_number", "feedback"],
            rows=[
                {
                    "roll_number": "CS/2026-01",
                    "feedback": (
                        "First Normal Form 1NF requires atomic attribute values and removes repeating groups. "
                        "Second Normal Form 2NF eliminates partial functional dependencies on composite keys. "
                        "Third Normal Form 3NF removes transitive functional dependencies and BCNF requires every determinant to be a candidate key."
                    ),
                },
                {
                    "roll_number": "CS/2026-02",
                    "feedback": (
                        "Left outer join returns all rows from the left table and fills unmatched right columns with NULL. "
                        "Cross join computes the Cartesian product of two tables."
                    ),
                },
            ],
        )

        # CSV 2 in another directory with custom student ID & feedback column names
        csv_lect2 = _write_csv(
            tmp_path / "another_folder_B" / "joins_survey_responses.csv",
            fieldnames=["student_code", "reflection_text"],
            rows=[
                {
                    "student_code": "STU_900",
                    "reflection_text": (
                        "SQL inner join returns rows matching the join condition in both tables. "
                        "Left outer join preserves unmatched left table rows with NULL padding, while cross join forms the Cartesian product."
                    ),
                }
            ],
        )

        # Force deterministic fallback by clearing LLM keys in this test scope
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "", "GEMINI_API_KEY": ""}, clear=False):
            summary_1 = run_verification_pipeline(
                course_id="DBMS",
                lecture_id="DBMS_lect1",
                feedback_csv=csv_lect1,
                data_root=data_root,
            )
            summary_2 = run_verification_pipeline(
                course_id="DBMS",
                lecture_id="DBMS_lect2",
                feedback_csv=csv_lect2,
                student_id_column="student_code",
                feedback_column="reflection_text",
                data_root=data_root,
            )

        res_dir_1 = get_results_dir("DBMS", "DBMS_lect1", data_root=data_root)
        res_dir_2 = get_results_dir("DBMS", "DBMS_lect2", data_root=data_root)
        assert res_dir_1 != res_dir_2

        # Check sanitized per-student directories in Lecture 1
        stu1_dir = res_dir_1 / "CS_2026-01"
        stu2_dir = res_dir_1 / "CS_2026-02"
        assert stu1_dir.is_dir() and stu2_dir.is_dir()
        for sdir in (stu1_dir, stu2_dir):
            for fname in ("claims.json", "evidence.json", "evaluated.json", "score.json"):
                assert (sdir / fname).is_file()
        assert (res_dir_1 / "all_students_summary.json").is_file()

        # Check Lecture 2 student directory
        stu900_dir = res_dir_2 / "STU_900"
        assert stu900_dir.is_dir()
        for fname in ("claims.json", "evidence.json", "evaluated.json", "score.json"):
            assert (stu900_dir / fname).is_file()
        assert (res_dir_2 / "all_students_summary.json").is_file()

        # Verify Student 1 (wrote about Normalization) scored MUCH higher on DBMS_lect1
        # than Student 2 (who wrote about SQL Joins on DBMS_lect1!)
        score_s1 = json.loads((stu1_dir / "score.json").read_text(encoding="utf-8"))
        score_s2 = json.loads((stu2_dir / "score.json").read_text(encoding="utf-8"))
        score_s900 = json.loads((stu900_dir / "score.json").read_text(encoding="utf-8"))

        assert score_s1["scores"]["total"]["score"] > score_s2["scores"]["total"]["score"]
        assert score_s1["scores"]["lecture_coverage"]["score"] > score_s2["scores"]["lecture_coverage"]["score"]
        assert score_s900["scores"]["total"]["score"] > 5.0

        # Confirm every evidence item in Lecture 1 results strictly comes from DBMS_lect1
        ev_s2 = json.loads((stu2_dir / "evidence.json").read_text(encoding="utf-8"))
        for claim_obj in ev_s2["claims"]:
            for ev in claim_obj["evidence"]:
                assert ev["course_id"] == "DBMS"
                assert ev["lecture_id"] == "DBMS_lect1"

        assert summary_1["total_students"] == 2
        assert summary_2["total_students"] == 1


def test_9_cli_requires_explicit_arguments_no_silent_defaults():
    """
    Tests Mandatory Requirement 9:
      No default lecture or CSV is silently selected when CLI arguments are omitted.
    """
    commands = [
        [sys.executable, str(PROJECT_ROOT / "backend" / "run_lecture_pipeline.py")],
        [
            sys.executable,
            str(PROJECT_ROOT / "backend" / "run_lecture_pipeline.py"),
            "--course-id",
            "DBMS",
        ],
        [sys.executable, str(PROJECT_ROOT / "backend" / "verification" / "pipeline.py")],
        [
            sys.executable,
            str(PROJECT_ROOT / "backend" / "verification" / "pipeline.py"),
            "--course-id",
            "DBMS",
            "--lecture-id",
            "DBMS_lect1",
        ],
        [sys.executable, str(PROJECT_ROOT / "backend" / "retrival" / "search.py")],
        [sys.executable, str(PROJECT_ROOT / "backend" / "retrival" / "build_index.py")],
    ]
    for cmd in commands:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode != 0, f"Expected non-zero exit code when running without required args: {cmd}"


def test_10_comprehensive_validation_and_error_handling():
    """
    Tests Mandatory Requirement 10 & Section 9 safety checks:
      - Invalid identifiers (empty, path traversal)
      - Missing audio / PDF files and unsupported extensions
      - Missing lecture knowledge base
      - Mismatched FAISS vector count vs chunk_mapping.json length
      - Missing CSV columns, duplicate student IDs, sanitized ID collisions, empty feedback
      - API failure handling & secret redaction
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        data_root = tmp_path / "backend_data"

        # A. Invalid identifiers
        for bad_id in ["", "   ", "../hack", "DBMS/lect1", "lect:1"]:
            raised = False
            try:
                get_lecture_paths(bad_id, "lect1", data_root=data_root)
            except ValueError:
                raised = True
            assert raised, f"Expected ValueError for invalid identifier: {bad_id!r}"

        # B. Missing audio/PDF files
        pdf_ok = _create_pdf(tmp_path / "valid.pdf", ["Some valid PDF text on slide one."])
        audio_ok = _create_dummy_wav(tmp_path / "valid.wav")

        try:
            run_pipeline(
                course_id="DBMS",
                lecture_id="L1",
                course_name="Databases",
                lecture_title="Intro",
                audio_path=tmp_path / "nonexistent.mp3",
                pdf_path=pdf_ok,
                data_root=data_root,
            )
            assert False, "Expected FileNotFoundError for missing audio"
        except FileNotFoundError:
            pass

        # C. Unsupported format
        bad_ext = tmp_path / "notes.txt"
        bad_ext.write_text("hello", encoding="utf-8")
        try:
            run_pipeline(
                course_id="DBMS",
                lecture_id="L1",
                course_name="Databases",
                lecture_title="Intro",
                audio_path=audio_ok,
                pdf_path=bad_ext,
                data_root=data_root,
            )
            assert False, "Expected ValueError for unsupported PDF extension"
        except ValueError:
            pass

        # D. Missing lecture knowledge base
        valid_csv = _write_csv(
            tmp_path / "students.csv",
            ["roll_number", "feedback"],
            [{"roll_number": "1", "feedback": "Normalization removes redundancy."}],
        )
        try:
            run_verification_pipeline(
                course_id="DBMS",
                lecture_id="MISSING_LECT",
                feedback_csv=valid_csv,
                data_root=data_root,
            )
            assert False, "Expected FileNotFoundError for missing knowledge base"
        except FileNotFoundError:
            pass

        # E. Mismatched FAISS index vs chunk_mapping length
        _ingest_two_dbms_lectures(data_root, tmp_path)
        p1 = get_lecture_paths("DBMS", "DBMS_lect1", data_root=data_root)
        mapping_data = json.loads(p1.chunk_mapping.read_text(encoding="utf-8"))
        corrupted_mapping = mapping_data[:-1]  # Drop last item to induce length mismatch
        p1.chunk_mapping.write_text(json.dumps(corrupted_mapping), encoding="utf-8")

        try:
            validate_and_load_knowledge_base("DBMS", "DBMS_lect1", data_root=data_root)
            assert False, "Expected ValueError for mismatched FAISS vs mapping lengths"
        except ValueError as exc:
            assert "mismatch" in str(exc).lower()

        # F. Missing CSV columns
        bad_col_csv = _write_csv(
            tmp_path / "bad_cols.csv",
            ["id_wrong", "comments"],
            [{"id_wrong": "1", "comments": "Text"}],
        )
        try:
            load_and_validate_feedback_csv(bad_col_csv)
            assert False, "Expected ValueError for missing CSV columns"
        except ValueError as exc:
            assert "column" in str(exc).lower()

        # G. Duplicate student IDs & sanitized collisions
        dup_csv = _write_csv(
            tmp_path / "dup.csv",
            ["roll_number", "feedback"],
            [
                {"roll_number": "101", "feedback": "Valid feedback one."},
                {"roll_number": "101", "feedback": "Duplicate student feedback."},
            ],
        )
        try:
            load_and_validate_feedback_csv(dup_csv)
            assert False, "Expected ValueError for duplicate student ID"
        except ValueError as exc:
            assert "duplicate" in str(exc).lower()

        collision_csv = _write_csv(
            tmp_path / "collision.csv",
            ["roll_number", "feedback"],
            [
                {"roll_number": "A/1", "feedback": "Valid feedback one."},
                {"roll_number": "A_1", "feedback": "Colliding sanitized student ID."},
            ],
        )
        try:
            load_and_validate_feedback_csv(collision_csv)
            assert False, "Expected ValueError for sanitized student ID collision"
        except ValueError as exc:
            assert "collision" in str(exc).lower()

        # H. Empty feedback
        empty_fb_csv = _write_csv(
            tmp_path / "empty_fb.csv",
            ["roll_number", "feedback"],
            [{"roll_number": "105", "feedback": "    "}],
        )
        try:
            load_and_validate_feedback_csv(empty_fb_csv)
            assert False, "Expected ValueError for empty feedback"
        except ValueError as exc:
            assert "empty feedback" in str(exc).lower()

        # I. API failure handling + secret redaction
        fake_secret = "sk-or-v1-supersecretkey999999999"
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": fake_secret, "GEMINI_API_KEY": ""}, clear=False):
            redacted = redact_secrets(f"Failed with Authorization Bearer {fake_secret}")
            assert fake_secret not in redacted
            assert "[REDACTED]" in redacted

            with patch("requests.post", side_effect=OSError(f"Connection failed for {fake_secret}")):
                try:
                    call_llm_json("Test prompt", strict_llm=True)
                    assert False, "Expected LLMAPIError in strict_llm mode"
                except LLMAPIError as exc:
                    assert fake_secret not in str(exc)


def test_cache_reuse_only_when_identity_and_config_match():
    """
    Proves cached transcription is reused ONLY when course_id, lecture_id, audio SHA-256,
    and whisper_model match, and reprocesses when file content or model changes.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        data_root = tmp_path / "backend_data"
        audio_a = _create_dummy_wav(tmp_path / "lect_audio.wav", freq_offset=2)
        pdf_a = _create_pdf(tmp_path / "lect_slides.pdf", ["Relational algebra selection and projection operators."])

        call_counter = {"count": 0}

        def counted_transcribe(audio_path: str, lecture_id: str, course_id=None, model_size="base", device=None, chunk_length_sec=180):
            call_counter["count"] += 1
            return {
                "course_id": course_id,
                "lecture_id": lecture_id,
                "source_file": Path(audio_path).name,
                "source_sha256": compute_file_sha256(audio_path),
                "whisper_model": model_size,
                "segments": [
                    {
                        "start": 0.0,
                        "end": 12.0,
                        "text": "Selection filters rows while projection chooses columns in relational algebra.",
                    }
                ],
            }

        with patch("backend.ingestion.audio.transcribe_audio", side_effect=counted_transcribe):
            # Initial run -> transcribes (count = 1)
            run_pipeline(
                course_id="DBMS",
                lecture_id="DBMS_alg",
                course_name="Database Management Systems",
                lecture_title="Relational Algebra",
                audio_path=audio_a,
                pdf_path=pdf_a,
                whisper_model="base",
                data_root=data_root,
            )
            assert call_counter["count"] == 1

            # Second run with identical inputs & config -> reuses cache (count remains 1)
            run_pipeline(
                course_id="DBMS",
                lecture_id="DBMS_alg",
                course_name="Database Management Systems",
                lecture_title="Relational Algebra",
                audio_path=audio_a,
                pdf_path=pdf_a,
                whisper_model="base",
                data_root=data_root,
            )
            assert call_counter["count"] == 1

            # Different whisper_model -> must re-transcribe (count = 2)
            run_pipeline(
                course_id="DBMS",
                lecture_id="DBMS_alg",
                course_name="Database Management Systems",
                lecture_title="Relational Algebra",
                audio_path=audio_a,
                pdf_path=pdf_a,
                whisper_model="tiny",
                data_root=data_root,
            )
            assert call_counter["count"] == 2

            # Different audio file content (different SHA-256) -> must re-transcribe (count = 3)
            audio_modified = _create_dummy_wav(tmp_path / "lect_audio_v2.wav", freq_offset=9)
            run_pipeline(
                course_id="DBMS",
                lecture_id="DBMS_alg",
                course_name="Database Management Systems",
                lecture_title="Relational Algebra",
                audio_path=audio_modified,
                pdf_path=pdf_a,
                whisper_model="tiny",
                data_root=data_root,
            )
            assert call_counter["count"] == 3


if __name__ == "__main__":
    test_1_2_3_4_separate_directories_kbs_and_reprocessing_isolation()
    print("[PASSED] test_1_2_3_4_separate_directories_kbs_and_reprocessing_isolation")
    test_5_6_strict_retrieval_cross_lecture_isolation()
    print("[PASSED] test_5_6_strict_retrieval_cross_lecture_isolation")
    test_7_8_11_dynamic_verification_student_directories_custom_csv_and_scoring()
    print("[PASSED] test_7_8_11_dynamic_verification_student_directories_custom_csv_and_scoring")
    test_9_cli_requires_explicit_arguments_no_silent_defaults()
    print("[PASSED] test_9_cli_requires_explicit_arguments_no_silent_defaults")
    test_10_comprehensive_validation_and_error_handling()
    print("[PASSED] test_10_comprehensive_validation_and_error_handling")
    test_cache_reuse_only_when_identity_and_config_match()
    print("[PASSED] test_cache_reuse_only_when_identity_and_config_match")
