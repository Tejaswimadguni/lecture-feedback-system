import re
from typing import List, Dict, Any


FILLER_WORDS_REGEX = re.compile(r"(?i)\b(?:uh|um|erm|hmm|ah|er)\b\s*,?\s*")


def clean_segment_text(text: str) -> str:
    """
    Cleans raw transcript segment text by removing extra spaces, line breaks,
    transcription artifacts, and filler words (e.g. 'uh', 'um', 'erm', 'hmm').
    """
    if not text:
        return ""

    # Remove HTML/subtitle styling tags if present (e.g. <font color="...">)
    cleaned = re.sub(r"<[^>]+>", "", text)

    # Convert non-breaking spaces and zero-width spaces to standard space
    cleaned = cleaned.replace("\u00a0", " ").replace("\u200b", "")

    # Remove filler words (e.g. 'uh', 'um', 'erm', 'hmm', including repeated ones and trailing commas)
    cleaned = FILLER_WORDS_REGEX.sub("", cleaned)

    # Clean up residual multiple commas (e.g. ", ,") or leading commas
    cleaned = re.sub(r"\s*,\s*,", ",", cleaned)
    cleaned = re.sub(r"^\s*,\s*", "", cleaned)

    # Replace multiple whitespace characters (tabs, newlines, repeated spaces) with a single space
    cleaned = re.sub(r"\s+", " ", cleaned)

    # Trim leading and trailing whitespace
    return cleaned.strip()


def clean_transcript(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Cleans transcript segments by stripping transcription noise and filler words
    while preserving start and end timestamps.

    Args:
        segments: List of segment dicts with keys 'start', 'end', and 'text'.

    Returns:
        List of cleaned segment dicts with preserved timestamps.
    """
    cleaned_segments = []
    for seg in segments:
        text = seg.get("text", "")
        cleaned_text = clean_segment_text(text)

        # Only retain segments that contain actual text content
        if cleaned_text:
            cleaned_segments.append({
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "text": cleaned_text,
            })

    return cleaned_segments
