import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.paths import (
    compute_file_sha256,
    get_lecture_paths,
    validate_identifier,
    validate_pdf_file,
)


def extract_pdf_text(
    pdf_path: str,
    lecture_id: str,
    course_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extracts text from a PDF file page by page using PyMuPDF (or pypdf fallback).

    Args:
        pdf_path: Path to the input PDF file.
        lecture_id: Explicit identifier for the lecture (required).
        course_id: Optional course identifier to store in raw extraction metadata.

    Returns:
        Dict containing explicit identifiers, source metadata, and 1-indexed page objects.
    """
    valid_pdf = validate_pdf_file(pdf_path)
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")
    valid_course_id = validate_identifier(course_id, "course_id") if course_id is not None else None

    pages = []

    # Try pymupdf first, fallback to pypdf if DLL loading is blocked on Windows
    try:
        import pymupdf
        doc = pymupdf.open(str(valid_pdf))
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            pages.append({
                "page": page_num + 1,
                "text": text.strip(),
            })
        doc.close()
    except Exception:
        # Pure Python fallback using pypdf (no C-extension / DLL dependencies)
        try:
            import pypdf
            reader = pypdf.PdfReader(str(valid_pdf))
            for page_num, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                pages.append({
                    "page": page_num,
                    "text": text.strip(),
                })
        except ImportError as e:
            raise ImportError(
                "Neither PyMuPDF nor pypdf could be loaded. Install pypdf using: pip install pypdf"
            ) from e

    payload: Dict[str, Any] = {
        "lecture_id": valid_lecture_id,
        "source_file": valid_pdf.name,
        "source_sha256": compute_file_sha256(valid_pdf),
        "pages": pages,
    }
    if valid_course_id is not None:
        payload["course_id"] = valid_course_id
    return payload


def save_pdf_text_json(
    pdf_path: str,
    course_id: str,
    lecture_id: str,
    output_path: Optional[str] = None,
    data_root: Optional[str] = None,
) -> str:
    """
    Extracts text from PDF and saves it to the lecture's isolated processed path
    (or an explicitly supplied output_path).
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")

    data = extract_pdf_text(
        pdf_path=pdf_path,
        lecture_id=valid_lecture_id,
        course_id=valid_course_id,
    )

    if output_path:
        dest = Path(output_path).resolve()
    else:
        lpaths = get_lecture_paths(valid_course_id, valid_lecture_id, data_root=data_root)
        dest = lpaths.pdf_raw

    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return str(dest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest PDF lecture notes/slides into structured JSON.")
    parser.add_argument("--pdf", required=True, help="Path to input PDF file.")
    parser.add_argument("--course-id", required=True, help="Explicit course identifier.")
    parser.add_argument("--lecture-id", required=True, help="Explicit lecture identifier.")
    parser.add_argument("--output", "-o", default=None, help="Optional explicit output JSON path.")
    parser.add_argument("--data-root", default=None, help="Optional custom data root directory.")

    args = parser.parse_args()
    try:
        saved_path = save_pdf_text_json(
            pdf_path=args.pdf,
            course_id=args.course_id,
            lecture_id=args.lecture_id,
            output_path=args.output,
            data_root=args.data_root,
        )
        print(f"Successfully processed PDF into JSON: {saved_path}")
    except Exception as e:
        print(f"Error processing PDF: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
