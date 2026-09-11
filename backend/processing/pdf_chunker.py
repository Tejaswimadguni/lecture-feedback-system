from typing import List, Dict, Any, Optional

try:
    from .metadata import create_chunk_metadata
except ImportError:
    from metadata import create_chunk_metadata


def count_words(text: str) -> int:
    """Counts words in a text string."""
    return len(text.split())


def chunk_pdf(
    pages: List[Dict[str, Any]],
    course_id: str = "MIT_6_100L",
    lecture_id: str = "lec01",
    target_word_count: int = 350,
    course_name: str = "Introduction to CS",
    lecture_title: str = "Introduction",
    source_file: str = "lecture_01.pdf",
) -> List[Dict[str, Any]]:
    """
    Page-aware PDF chunker. Groups page text into chunks while preserving exact page numbers.

    Args:
        pages: Cleaned PDF page dictionaries [{'page': int, 'text': str}].
        course_id: Identifier for the course.
        lecture_id: Identifier for the lecture.
        target_word_count: Target maximum words per chunk on a page before splitting.
        course_name: Full name of the course.
        lecture_title: Title of the lecture.
        source_file: PDF source filename.

    Returns:
        List of chunk dicts formatted according to the unified metadata schema.
    """
    if not pages:
        return []

    chunks = []

    for page_info in pages:
        page_num = page_info["page"]
        text = page_info["text"]

        if not text or not text.strip():
            continue

        words = text.split()
        total_words = len(words)

        if total_words <= target_word_count:
            chunk_id = f"{course_id}_{lecture_id}_P{page_num:02d}_C01"
            chunk = create_chunk_metadata(
                chunk_id=chunk_id,
                course_id=course_id,
                lecture_id=lecture_id,
                source_type="pdf",
                text=text.strip(),
                course_name=course_name,
                lecture_title=lecture_title,
                source_file=source_file,
                start_time=None,
                end_time=None,
                page=page_num,
            )
            chunks.append(chunk)
        else:
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            current_paras = []
            current_words = 0
            chunk_sub_idx = 1

            for para in paragraphs:
                para_word_cnt = count_words(para)
                if current_words + para_word_cnt > target_word_count and current_paras:
                    chunk_text = "\n\n".join(current_paras)
                    chunk_id = f"{course_id}_{lecture_id}_P{page_num:02d}_C{chunk_sub_idx:02d}"
                    chunk = create_chunk_metadata(
                        chunk_id=chunk_id,
                        course_id=course_id,
                        lecture_id=lecture_id,
                        source_type="pdf",
                        text=chunk_text,
                        course_name=course_name,
                        lecture_title=lecture_title,
                        source_file=source_file,
                        start_time=None,
                        end_time=None,
                        page=page_num,
                    )
                    chunks.append(chunk)
                    chunk_sub_idx += 1
                    current_paras = [para]
                    current_words = para_word_cnt
                else:
                    current_paras.append(para)
                    current_words += para_word_cnt

            if current_paras:
                chunk_text = "\n\n".join(current_paras)
                chunk_id = f"{course_id}_{lecture_id}_P{page_num:02d}_C{chunk_sub_idx:02d}"
                chunk = create_chunk_metadata(
                    chunk_id=chunk_id,
                    course_id=course_id,
                    lecture_id=lecture_id,
                    source_type="pdf",
                    text=chunk_text,
                    course_name=course_name,
                    lecture_title=lecture_title,
                    source_file=source_file,
                    start_time=None,
                    end_time=None,
                    page=page_num,
                )
                chunks.append(chunk)

    return chunks
