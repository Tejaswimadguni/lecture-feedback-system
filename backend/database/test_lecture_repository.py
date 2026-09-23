from lecture_repository import (
    create_lecture,
    save_lecture_source,
)


def main():
    lecture_id = create_lecture(
        lecture_id="lecture_01",
        lecture_number=1,
        lecture_title="Introduction to Machine Learning",
        description="Lecture 1 test record"
    )

    print(f"✅ Lecture created: {lecture_id}")

    audio_id = save_lecture_source(
        lecture_id="lecture_01",
        source_type="AUDIO",
        file_name="lecture_01.mp3",
        file_path="data/raw/audio/lecture_01.mp3"
    )

    print(f"✅ Audio source created: {audio_id}")

    pdf_id = save_lecture_source(
        lecture_id="lecture_01",
        source_type="PDF",
        file_name="lecture_01.pdf",
        file_path="data/raw/pdf/lecture_01.pdf"
    )

    print(f"✅ PDF source created: {pdf_id}")

    ppt_id = save_lecture_source(
        lecture_id="lecture_01",
        source_type="PPT",
        file_name="lecture_01.pptx",
        file_path="data/raw/ppt/lecture_01.pptx"
    )

    print(f"✅ PPT source created: {ppt_id}")


if __name__ == "__main__":
    main()