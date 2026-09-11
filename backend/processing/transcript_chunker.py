from typing import List, Dict, Any, Optional

try:
    from .metadata import create_chunk_metadata
except ImportError:
    from metadata import create_chunk_metadata


def count_words(text: str) -> int:
    """Counts words in a text string."""
    return len(text.split())


def chunk_transcript(
    segments: List[Dict[str, Any]],
    course_id: str = "MIT_6_100L",
    lecture_id: str = "lec01",
    target_word_count: int = 350,
    overlap_word_count: int = 50,
    course_name: str = "Introduction to CS",
    lecture_title: str = "Introduction",
    source_file: str = "lecture_01.mp4",
) -> List[Dict[str, Any]]:
    """
    Chunks transcript segments based on cumulative word count while preserving start and end timestamps.

    Args:
        segments: Cleaned transcript segment objects [{'start': float, 'end': float, 'text': str}].
        course_id: Unique identifier for the course.
        lecture_id: Unique identifier for the lecture.
        target_word_count: Target number of words per chunk (default ~350).
        overlap_word_count: Target number of overlapping words between consecutive chunks (default ~50).
        course_name: Name of the course.
        lecture_title: Title of the lecture.
        source_file: Audio/video source filename.

    Returns:
        List of chunk dictionaries formatted according to the unified metadata schema.
    """
    if not segments:
        return []

    chunks = []
    chunk_index = 1

    start_idx = 0
    num_segments = len(segments)

    while start_idx < num_segments:
        current_window = []
        current_words = 0
        end_idx = start_idx

        # Accumulate segments until target_word_count is reached
        while end_idx < num_segments:
            seg = segments[end_idx]
            seg_words = count_words(seg["text"])
            current_window.append(seg)
            current_words += seg_words
            end_idx += 1

            if current_words >= target_word_count:
                break

        # Build chunk text and timestamps from accumulated segments
        chunk_text = " ".join(seg["text"] for seg in current_window)
        start_time = current_window[0]["start"]
        end_time = current_window[-1]["end"]

        chunk_id = f"{course_id}_{lecture_id}_T{chunk_index:03d}"

        chunk = create_chunk_metadata(
            chunk_id=chunk_id,
            course_id=course_id,
            lecture_id=lecture_id,
            source_type="transcript",
            text=chunk_text,
            course_name=course_name,
            lecture_title=lecture_title,
            source_file=source_file,
            start_time=start_time,
            end_time=end_time,
            page=None,
        )
        chunks.append(chunk)
        chunk_index += 1

        # If we reached the end of segments, break
        if end_idx >= num_segments:
            break

        # Determine next start_idx using overlap_word_count
        overlap_words = 0
        next_start = end_idx
        for i in range(end_idx - 1, start_idx, -1):
            w = count_words(segments[i]["text"])
            if overlap_words + w <= overlap_word_count or next_start == end_idx:
                overlap_words += w
                next_start = i
            else:
                break

        if next_start <= start_idx:
            next_start = start_idx + 1

        start_idx = next_start

    return chunks
