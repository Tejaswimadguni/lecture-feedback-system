import argparse
import json
import os
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
)


def extract_ppt_text(
    ppt_path: str,
    lecture_id: str,
    course_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extracts text from a PowerPoint (.pptx) file slide by slide using python-pptx.

    Args:
        ppt_path: Path to the input PPTX file.
        lecture_id: Explicit identifier for the lecture (required).
        course_id: Optional course identifier.

    Returns:
        Dict containing lecture_id and a list of page objects with 1-indexed slide numbers and text.
    """
    if not ppt_path or not os.path.exists(ppt_path):
        raise FileNotFoundError(f"PPT file not found at: {ppt_path}")

    p = Path(ppt_path).resolve()
    if p.suffix.lower() not in {".pptx", ".ppt"}:
        raise ValueError(f"Unsupported PowerPoint format '{p.suffix}'. Expected '.pptx' or '.ppt'.")

    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")
    valid_course_id = validate_identifier(course_id, "course_id") if course_id is not None else None

    try:
        from pptx import Presentation
    except ImportError as e:
        raise ImportError("python-pptx package is required. Install it using: pip install python-pptx") from e

    prs = Presentation(str(p))
    pages = []

    for idx, slide in enumerate(prs.slides, start=1):
        slide_text_pieces = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    text = paragraph.text.strip()
                    if text:
                        slide_text_pieces.append(text)

        full_slide_text = "\n".join(slide_text_pieces).strip()
        pages.append({
            "page": idx,
            "text": full_slide_text,
        })

    payload: Dict[str, Any] = {
        "lecture_id": valid_lecture_id,
        "source_file": p.name,
        "source_sha256": compute_file_sha256(p),
        "pages": pages,
    }
    if valid_course_id is not None:
        payload["course_id"] = valid_course_id
    return payload


def save_ppt_text_json(
    ppt_path: str,
    course_id: str,
    lecture_id: str,
    output_path: Optional[str] = None,
    data_root: Optional[str] = None,
) -> str:
    """
    Extracts text from PPTX and saves it to an explicit or lecture-specific JSON path.
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")

    data = extract_ppt_text(ppt_path=ppt_path, lecture_id=valid_lecture_id, course_id=valid_course_id)

    if output_path:
        dest = Path(output_path).resolve()
    else:
        lpaths = get_lecture_paths(valid_course_id, valid_lecture_id, data_root=data_root)
        dest = lpaths.processed_dir / "ppt_raw.json"

    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return str(dest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest PowerPoint presentation slides into structured JSON.")
    parser.add_argument("--ppt", required=True, help="Path to input PPTX file.")
    parser.add_argument("--course-id", required=True, help="Explicit course identifier.")
    parser.add_argument("--lecture-id", required=True, help="Explicit lecture identifier.")
    parser.add_argument("--output", "-o", default=None, help="Optional path to output JSON file.")
    parser.add_argument("--data-root", default=None, help="Optional custom data root directory.")

    args = parser.parse_args()
    try:
        saved_path = save_ppt_text_json(
            ppt_path=args.ppt,
            course_id=args.course_id,
            lecture_id=args.lecture_id,
            output_path=args.output,
            data_root=args.data_root,
        )
        print(f"Successfully processed PPT into JSON: {saved_path}")
    except Exception as e:
        print(f"Error processing PPT: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
