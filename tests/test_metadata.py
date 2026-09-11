import contextlib
from backend.processing.metadata import create_chunk_metadata, validate_chunk, build_dataset_metadata


@contextlib.contextmanager
def assert_raises(exception_type):
    """Simple context manager replacement for pytest.raises."""
    raised = False
    try:
        yield
    except exception_type:
        raised = True
    assert raised, f"Expected exception {exception_type} was not raised."


def test_transcript_chunk_metadata_schema():
    chunk = create_chunk_metadata(
        chunk_id="MIT_6_100L_lec01_T001",
        course_id="MIT_6_100L",
        lecture_id="lec01",
        source_type="transcript",
        text="Today we are going to discuss variables.",
        course_name="Introduction to CS",
        lecture_title="Introduction",
        source_file="lecture_01.mp4",
        start_time=0.0,
        end_time=12.5,
        page=None
    )

    assert chunk["chunk_id"] == "MIT_6_100L_lec01_T001"
    assert chunk["course_id"] == "MIT_6_100L"
    assert chunk["course_name"] == "Introduction to CS"
    assert chunk["lecture_id"] == "lec01"
    assert chunk["lecture_title"] == "Introduction"
    assert chunk["source_type"] == "transcript"
    assert chunk["source_file"] == "lecture_01.mp4"
    assert chunk["text"] == "Today we are going to discuss variables."
    assert chunk["start_time"] == 0.0
    assert chunk["end_time"] == 12.5
    assert chunk["page"] is None

    assert validate_chunk(chunk) is True


def test_pdf_chunk_metadata_schema():
    chunk = create_chunk_metadata(
        chunk_id="MIT_6_100L_lec01_P04_C01",
        course_id="MIT_6_100L",
        lecture_id="lec01",
        source_type="pdf",
        text="A variable is a name that refers to a value.",
        course_name="Introduction to CS",
        lecture_title="Introduction",
        source_file="lecture_01.pdf",
        start_time=None,
        end_time=None,
        page=4
    )

    assert chunk["chunk_id"] == "MIT_6_100L_lec01_P04_C01"
    assert chunk["course_id"] == "MIT_6_100L"
    assert chunk["course_name"] == "Introduction to CS"
    assert chunk["lecture_id"] == "lec01"
    assert chunk["lecture_title"] == "Introduction"
    assert chunk["source_type"] == "pdf"
    assert chunk["source_file"] == "lecture_01.pdf"
    assert chunk["text"] == "A variable is a name that refers to a value."
    assert chunk["start_time"] is None
    assert chunk["end_time"] is None
    assert chunk["page"] == 4

    assert validate_chunk(chunk) is True


def test_invalid_chunk_metadata_raises():
    with assert_raises(ValueError):
        create_chunk_metadata(
            chunk_id="invalid_chunk",
            course_id="MIT",
            lecture_id="lec01",
            source_type="invalid_type",
            text="some text"
        )

    # Transcript chunk missing start_time
    with assert_raises(ValueError):
        create_chunk_metadata(
            chunk_id="t_chunk",
            course_id="MIT",
            lecture_id="lec01",
            source_type="transcript",
            text="some text",
            start_time=None,
            end_time=10.0
        )

    # PDF chunk missing page
    with assert_raises(ValueError):
        create_chunk_metadata(
            chunk_id="p_chunk",
            course_id="MIT",
            lecture_id="lec01",
            source_type="pdf",
            text="some text",
            page=None
        )


def test_build_dataset_metadata():
    c1 = create_chunk_metadata("MIT_6_100L_lec01_T001", "MIT_6_100L", "lec01", "transcript", "hello", start_time=0.0, end_time=5.0)
    c2 = create_chunk_metadata("MIT_6_100L_lec01_P01_C01", "MIT_6_100L", "lec01", "pdf", "world", page=1)

    summary = build_dataset_metadata([c1, c2])

    assert summary["total_chunks"] == 2
    assert summary["total_transcript_chunks"] == 1
    assert summary["total_pdf_chunks"] == 1
    assert summary["courses"] == ["MIT_6_100L"]
    assert summary["lectures"] == ["lec01"]
