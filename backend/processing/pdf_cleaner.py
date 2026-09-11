import re
from typing import List, Dict, Any, Optional


def clean_pdf_page_text(text: str, custom_headers: Optional[List[str]] = None) -> str:
    """
    Cleans extracted PDF page text by removing headers, footers, standalone page numbers,
    broken line hyphenations, and excessive whitespace while preserving equations, definitions,
    headings, and technical terms.

    Args:
        text: Raw extracted text of a PDF page.
        custom_headers: Optional list of explicit header strings to strip.

    Returns:
        Cleaned text string.
    """
    if not text:
        return ""

    cleaned = text

    # Remove custom headers if supplied
    if custom_headers:
        for header in custom_headers:
            if header:
                cleaned = cleaned.replace(header, "")

    # Fix broken hyphenated words across line breaks (e.g. "com-\nputation" -> "computation")
    cleaned = re.sub(r"(\b[a-zA-Z]+)-\s*\n\s*([a-zA-Z]+\b)", r"\1\2", cleaned)

    # Remove common slide/lecture header/footer patterns (e.g., "6.100L Lecture 1", "6.0001 LECTURE 1")
    cleaned = re.sub(r"(?i)6\.\d+L?\s+Lecture\s+\d+", "", cleaned)
    cleaned = re.sub(r"(?i)6\.0001\s+LECTURE\s+\d+", "", cleaned)

    # Split into lines for page number and header filtering
    lines = cleaned.splitlines()
    filtered_lines = []

    total_lines = len(lines)
    for idx, line in enumerate(lines):
        stripped = line.strip()

        # Filter out standalone page numbers at the very beginning or end of page text
        if stripped.isdigit() and (idx == 0 or idx == total_lines - 1 or idx == total_lines - 2):
            continue

        # Filter out repetitive header lines that match "LECTURE X" or "Lecture X" alone
        if re.match(r"(?i)^lecture\s+\d+$", stripped):
            continue

        filtered_lines.append(line)

    cleaned = "\n".join(filtered_lines)

    # Replace multiple spaces within lines with a single space
    cleaned = re.sub(r"[ \t]+", " ", cleaned)

    # Collapse 3 or more consecutive newlines into double newlines (preserving paragraph breaks)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()


def clean_pdf_pages(
    pages: List[Dict[str, Any]],
    custom_headers: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Cleans a list of PDF page dicts [{'page': int, 'text': str}].

    Args:
        pages: List of page dicts.
        custom_headers: Optional custom header/footer strings to remove.

    Returns:
        List of cleaned page dicts with non-empty text.
    """
    cleaned_pages = []

    for p in pages:
        page_num = p.get("page")
        raw_text = p.get("text", "")
        cleaned_text = clean_pdf_page_text(raw_text, custom_headers=custom_headers)

        if cleaned_text:
            cleaned_pages.append({
                "page": int(page_num),
                "text": cleaned_text
            })

    return cleaned_pages
