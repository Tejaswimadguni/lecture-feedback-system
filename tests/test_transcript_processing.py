from backend.processing.transcript_cleaner import clean_transcript
from backend.processing.transcript_chunker import chunk_transcript


def test_clean_transcript_removes_filler_words_and_preserves_timestamps():
    raw_segments = [
        {
            "start": 10.2,
            "end": 14.8,
            "text": "   uh today   we are going to uh discuss variables. "
        },
        {
            "start": 15.0,
            "end": 18.5,
            "text": "so variables basically are um names that..."
        },
        {
            "start": 19.0,
            "end": 20.0,
            "text": "    "  # Empty segment should be cleaned out
        }
    ]

    cleaned = clean_transcript(raw_segments)

    assert len(cleaned) == 2

    # Verify timestamps are strictly preserved
    assert cleaned[0]["start"] == 10.2
    assert cleaned[0]["end"] == 14.8
    assert cleaned[1]["start"] == 15.0
    assert cleaned[1]["end"] == 18.5

    # Verify whitespace is normalized and filler words ('uh', 'um') are removed
    assert cleaned[0]["text"] == "today we are going to discuss variables."
    assert cleaned[1]["text"] == "so variables basically are names that..."
    assert "uh" not in cleaned[0]["text"].split()
    assert "um" not in cleaned[1]["text"].split()


def test_chunk_transcript_timestamps_and_metadata():
    cleaned_segments = [
        {"start": 0.0, "end": 10.0, "text": "Welcome to the introductory lecture on computer programming."},
        {"start": 10.0, "end": 20.0, "text": "Today we will cover variables, types, and basic computations."},
        {"start": 20.0, "end": 30.0, "text": "A variable is a named storage location that holds a value."},
        {"start": 30.0, "end": 40.0, "text": "Python supports integers, floats, booleans, and string values."}
    ]

    chunks = chunk_transcript(
        segments=cleaned_segments,
        course_id="MIT_6_100L",
        lecture_id="lec01",
        target_word_count=15,  # small target for test chunking
        overlap_word_count=5,
        source_file="lecture_01.mp4"
    )

    assert len(chunks) >= 2

    for chunk in chunks:
        assert chunk["chunk_id"].startswith("MIT_6_100L_lec01_T")
        assert chunk["course_id"] == "MIT_6_100L"
        assert chunk["lecture_id"] == "lec01"
        assert chunk["source_type"] == "transcript"
        assert chunk["source_file"] == "lecture_01.mp4"
        assert chunk["text"]
        assert chunk["start_time"] is not None
        assert chunk["end_time"] is not None
        assert chunk["page"] is None
        assert chunk["start_time"] < chunk["end_time"]
