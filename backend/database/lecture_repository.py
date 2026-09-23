try:
    from .database import get_connection
except ImportError:
    from database import get_connection


def create_lecture(
    lecture_id,
    lecture_number=None,
    lecture_title=None,
    description=None
):
    """
    Create a lecture record if it does not already exist.
    Returns the lecture_id.
    """

    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO lectures
                (
                    lecture_id,
                    lecture_number,
                    lecture_title,
                    description
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (lecture_id)
                DO UPDATE SET
                    lecture_number = EXCLUDED.lecture_number,
                    lecture_title = EXCLUDED.lecture_title,
                    description = EXCLUDED.description
                RETURNING lecture_id;
                """,
                (
                    lecture_id,
                    lecture_number,
                    lecture_title,
                    description
                )
            )

            result = cursor.fetchone()[0]

        conn.commit()
        return result

    finally:
        conn.close()


def save_lecture_source(
    lecture_id,
    source_type,
    file_name,
    file_path,
    file_size=None
):
    """
    Save an original lecture source file.

    source_type:
        AUDIO
        VIDEO
        PDF
        PPT
    """

    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO lecture_sources
                (
                    lecture_id,
                    source_type,
                    file_name,
                    file_path,
                    file_size
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING source_id;
                """,
                (
                    lecture_id,
                    source_type,
                    file_name,
                    file_path,
                    file_size
                )
            )

            source_id = cursor.fetchone()[0]

        conn.commit()
        return source_id

    finally:
        conn.close()


def save_lecture_chunk(
    chunk_id,
    lecture_id,
    source_id,
    chunk_index,
    source_type,
    text,
    page_number=None,
    start_time=None,
    end_time=None
):
    """
    Save one processed lecture chunk.
    """

    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO lecture_chunks
                (
                    chunk_id,
                    lecture_id,
                    source_id,
                    chunk_index,
                    source_type,
                    text,
                    page_number,
                    start_time,
                    end_time
                )
                VALUES
                (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (chunk_id)
                DO UPDATE SET
                    lecture_id = EXCLUDED.lecture_id,
                    source_id = EXCLUDED.source_id,
                    chunk_index = EXCLUDED.chunk_index,
                    source_type = EXCLUDED.source_type,
                    text = EXCLUDED.text,
                    page_number = EXCLUDED.page_number,
                    start_time = EXCLUDED.start_time,
                    end_time = EXCLUDED.end_time
                RETURNING chunk_id;
                """,
                (
                    chunk_id,
                    lecture_id,
                    source_id,
                    chunk_index,
                    source_type,
                    text,
                    page_number,
                    start_time,
                    end_time
                )
            )

            result = cursor.fetchone()[0]

        conn.commit()
        return result

    finally:
        conn.close()