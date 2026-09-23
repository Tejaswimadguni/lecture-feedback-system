import json
from pathlib import Path

try:
    from .database import get_connection
except ImportError:
    from database import get_connection


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def load_chunks(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def normalize_source_type(source_type):
    mapping = {
        "transcript": "AUDIO",
        "audio": "AUDIO",
        "video": "VIDEO",
        "pdf": "PDF",
        "ppt": "PPT",
        "powerpoint": "PPT",
    }

    normalized = mapping.get(str(source_type).lower())

    if normalized is None:
        raise ValueError(
            f"Unsupported source type: {source_type}"
        )

    return normalized


def get_source_directory(source_type):
    directories = {
        "AUDIO": PROCESSED_DIR / "transcripts",
        "VIDEO": PROCESSED_DIR / "transcripts",
        "PDF": PROCESSED_DIR / "pdf_text",
        "PPT": PROCESSED_DIR / "ppt_text",
    }

    return directories[source_type]


def create_or_update_lecture(cursor, chunk):
    lecture_id = chunk["lecture_id"]

    lecture_number = None
    lecture_title = chunk.get("lecture_title")
    description = chunk.get("course_name")

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

    return cursor.fetchone()[0]


def get_or_create_source(
    cursor,
    lecture_id,
    source_type,
    file_name,
    file_path
):
    cursor.execute(
        """
        SELECT source_id
        FROM lecture_sources
        WHERE lecture_id = %s
          AND source_type = %s
          AND file_name = %s
        LIMIT 1;
        """,
        (
            lecture_id,
            source_type,
            file_name
        )
    )

    row = cursor.fetchone()

    if row:
        source_id = row[0]

        cursor.execute(
            """
            UPDATE lecture_sources
            SET file_path = %s
            WHERE source_id = %s;
            """,
            (
                file_path,
                source_id
            )
        )

        return source_id

    cursor.execute(
        """
        INSERT INTO lecture_sources
        (
            lecture_id,
            source_type,
            file_name,
            file_path
        )
        VALUES (%s, %s, %s, %s)
        RETURNING source_id;
        """,
        (
            lecture_id,
            source_type,
            file_name,
            file_path
        )
    )

    return cursor.fetchone()[0]


def save_chunk(
    cursor,
    chunk,
    lecture_id,
    source_id,
    source_type,
    chunk_index
):
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
            end_time = EXCLUDED.end_time;
        """,
        (
            chunk["chunk_id"],
            lecture_id,
            source_id,
            chunk_index,
            source_type,
            chunk["text"],
            chunk.get("page"),
            chunk.get("start_time"),
            chunk.get("end_time")
        )
    )


def process_chunk_file(file_path):
    print(f"\n📄 Processing: {file_path.name}")

    chunks = load_chunks(file_path)

    if not chunks:
        print("   ⚠️ Empty chunk file. Skipping.")
        return

    first_chunk = chunks[0]

    lecture_id = first_chunk["lecture_id"]

    source_type = normalize_source_type(
        first_chunk["source_type"]
    )

    source_file = first_chunk["source_file"]

    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            create_or_update_lecture(
                cursor,
                first_chunk
            )

            source_path = str(
                Path(
                    "data",
                    "raw",
                    source_type.lower(),
                    source_file
                )
            )

            source_id = get_or_create_source(
                cursor,
                lecture_id,
                source_type,
                source_file,
                source_path
            )

            for index, chunk in enumerate(chunks):

                save_chunk(
                    cursor=cursor,
                    chunk=chunk,
                    lecture_id=lecture_id,
                    source_id=source_id,
                    source_type=source_type,
                    chunk_index=index
                )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    print(f"   Lecture ID : {lecture_id}")
    print(f"   Source     : {source_type}")
    print(f"   File       : {source_file}")
    print(f"   Chunks     : {len(chunks)}")
    print("   ✅ Imported successfully")


def find_chunk_files():
    files = []

    for directory in [
        PROCESSED_DIR / "transcripts",
        PROCESSED_DIR / "pdf_text",
        PROCESSED_DIR / "ppt_text",
    ]:

        if not directory.exists():
            continue

        files.extend(
            directory.glob("*_chunks.json")
        )

    return sorted(files)


def main():
    print("\n===================================")
    print("LECTURE DATABASE IMPORTER")
    print("===================================\n")

    chunk_files = find_chunk_files()

    if not chunk_files:
        print("❌ No chunk files found.")
        return

    print(
        f"Found {len(chunk_files)} chunk file(s).\n"
    )

    for file_path in chunk_files:
        process_chunk_file(file_path)

    print("\n===================================")
    print("DATABASE IMPORT COMPLETE")
    print("===================================")


if __name__ == "__main__":
    main()