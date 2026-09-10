import os
import json
import argparse
from typing import Dict, Any, Optional


def derive_lecture_id(file_path: str) -> str:
    """Derives a lecture ID from a filename by stripping path and extension."""
    basename = os.path.basename(file_path)
    lecture_id, _ = os.path.splitext(basename)
    return lecture_id


def extract_pdf_text(pdf_path: str, lecture_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Extracts text from a PDF file page by page using PyMuPDF (or pypdf fallback).

    Args:
        pdf_path: Path to the input PDF file.
        lecture_id: Identifier for the lecture. If None, derived from filename.

    Returns:
        Dict containing lecture_id and a list of page objects with 1-indexed page numbers and text.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found at: {pdf_path}")

    if not lecture_id:
        lecture_id = derive_lecture_id(pdf_path)

    pages = []

    # Try pymupdf first, fallback to pypdf if DLL loading is blocked on Windows
    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            pages.append({
                "page": page_num + 1,
                "text": text.strip()
            })
        doc.close()
    except Exception:
        # Pure Python fallback using pypdf (no C-extension / DLL dependencies)
        try:
            import pypdf
            reader = pypdf.PdfReader(pdf_path)
            for page_num, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                pages.append({
                    "page": page_num,
                    "text": text.strip()
                })
        except ImportError as e:
            raise ImportError(
                "Neither PyMuPDF nor pypdf could be loaded. Install pypdf using: pip install pypdf"
            ) from e

    return {
        "lecture_id": lecture_id,
        "pages": pages
    }


def save_pdf_text_json(pdf_path: str, output_path: Optional[str] = None, lecture_id: Optional[str] = None) -> str:
    """
    Extracts text from PDF and saves it to a JSON file.

    Args:
        pdf_path: Path to the input PDF file.
        output_path: Path where JSON should be saved. If None, defaults to data/processed/pdf_text/<lecture_id>_notes.json.
        lecture_id: Identifier for the lecture. If None, derived from filename.

    Returns:
        Path to the saved JSON file.
    """
    data = extract_pdf_text(pdf_path, lecture_id=lecture_id)

    if not output_path:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        output_dir = os.path.join(base_dir, "data", "processed", "pdf_text")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{data['lecture_id']}_notes.json")
    else:
        parent_dir = os.path.dirname(os.path.abspath(output_path))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return output_path


def find_default_raw_pdf() -> Optional[str]:
    """Finds the first available raw PDF file in data/raw/pdf or data/raw/pdfs."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    search_dirs = [
        os.path.join(base_dir, "data", "raw", "pdf"),
        os.path.join(base_dir, "data", "raw", "pdfs"),
    ]

    for search_dir in search_dirs:
        if os.path.exists(search_dir):
            for filename in os.listdir(search_dir):
                if filename.lower().endswith(".pdf"):
                    return os.path.join(search_dir, filename)
    return None


def main():
    parser = argparse.ArgumentParser(description="Ingest PDF lecture notes into structured JSON.")
    parser.add_argument(
        "pdf_path",
        nargs="?",
        default=None,
        help="Path to input PDF file. If omitted, scans data/raw/pdf for PDF files."
    )
    parser.add_argument("--output", "-o", help="Optional path to output JSON file")
    parser.add_argument("--lecture-id", "-l", help="Optional lecture ID")

    args = parser.parse_args()
    pdf_path = args.pdf_path

    if not pdf_path:
        pdf_path = find_default_raw_pdf()
        if pdf_path:
            print(f"No pdf_path specified. Automatically using discovered raw file: {pdf_path}")
        else:
            print("Error: No pdf_path specified and no PDF files found in data/raw/pdf.")
            print("\nUsage example:")
            print("  python backend/ingestion/pdf.py data/raw/pdf/mit6_100l_f22_lec01.pdf")
            return

    saved_path = save_pdf_text_json(pdf_path, output_path=args.output, lecture_id=args.lecture_id)
    print(f"Successfully processed PDF into JSON: {saved_path}")


if __name__ == "__main__":
    main()
