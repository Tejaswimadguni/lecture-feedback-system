from backend.processing.pdf_cleaner import clean_pdf_pages
from backend.processing.pdf_chunker import chunk_pdf


def test_clean_pdf_removes_headers_footers_preserves_equations():
    raw_pages = [
        {
            "page": 1,
            "text": "INTRODUCTION TO CS\n1\n6.100L Lecture 1\nVariables are names that refer to values."
        },
        {
            "page": 2,
            "text": "NUMERICAL EXAMPLE\nSquare root of a number x is y such that y*y = x\nStart with a guess g.\n6.100L Lecture 1\n2"
        }
    ]

    cleaned = clean_pdf_pages(raw_pages)

    assert len(cleaned) == 2

    # Assert header and page numbers stripped
    assert "6.100L Lecture 1" not in cleaned[0]["text"]
    assert "6.100L Lecture 1" not in cleaned[1]["text"]

    # Assert content, equations, and definitions preserved
    assert "Variables are names that refer to values." in cleaned[0]["text"]
    assert "Square root of a number x is y such that y*y = x" in cleaned[1]["text"]
    assert "y*y = x" in cleaned[1]["text"]


def test_chunk_pdf_page_aware_and_metadata():
    cleaned_pages = [
        {
            "page": 4,
            "text": "PRACTICE\nPROBLEM SOLVING\nA variable is a name that refers to a value in memory."
        },
        {
            "page": 5,
            "text": "TOPICS\nSolving problems using computation\nPython programming language"
        }
    ]

    chunks = chunk_pdf(
        pages=cleaned_pages,
        course_id="MIT_6_100L",
        lecture_id="lec01",
        target_word_count=50,
        source_file="lecture_01.pdf"
    )

    assert len(chunks) == 2

    chunk_p4 = chunks[0]
    assert chunk_p4["chunk_id"] == "MIT_6_100L_lec01_P04_C01"
    assert chunk_p4["course_id"] == "MIT_6_100L"
    assert chunk_p4["lecture_id"] == "lec01"
    assert chunk_p4["source_type"] == "pdf"
    assert chunk_p4["source_file"] == "lecture_01.pdf"
    assert chunk_p4["page"] == 4
    assert chunk_p4["start_time"] is None
    assert chunk_p4["end_time"] is None
    assert "variable" in chunk_p4["text"]

    chunk_p5 = chunks[1]
    assert chunk_p5["chunk_id"] == "MIT_6_100L_lec01_P05_C01"
    assert chunk_p5["page"] == 5
