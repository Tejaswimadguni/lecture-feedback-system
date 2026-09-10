"""Deterministic, evidence-preserving chunking helpers."""

import re
from typing import Any, Dict, Iterable, List


def normalize_text(text: str) -> str:
    """Lightly clean extraction artifacts without changing source meaning."""
    replacements = {"\u00ef\u0082\u00a7": " ", "\u00e2\u0080\u009c": '"', "\u00e2\u0080\u009d": '"',
                    "\u00e2\u0080\u0099": "'", "\u00e2\u0080\u0093": "-", "\u00ef\u0083\u00a0": " "}
    for artifact, replacement in replacements.items():
        text = text.replace(artifact, replacement)
    return re.sub(r"\s+", " ", text).strip()


def audio_knowledge_chunks(segments: Iterable[Dict[str, Any]], target_chars: int = 700, max_chars: int = 1200) -> List[Dict[str, Any]]:
    """Group consecutive transcript segments into bounded chronological evidence."""
    chunks: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_chars
        if current:
            original = " ".join(str(segment.get("text", "")).strip() for segment in current).strip()
            if original:
                chunks.append({"start": current[0].get("start"), "end": current[-1].get("end"),
                               "original_text": original, "knowledge_text": normalize_text(original)})
        current, current_chars = [], 0

    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        if current and (current_chars + len(text) > max_chars or current_chars >= target_chars):
            flush()
        current.append(segment)
        current_chars += len(text) + 1
    flush()
    return chunks


def pdf_knowledge_chunks(pages: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep each extracted PDF page as independently traceable evidence."""
    return [{"page": page.get("page"), "original_text": text, "knowledge_text": normalize_text(text)}
            for page in pages if (text := str(page.get("text", "")).strip())]
