import json
import math
import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional


REQUIRED_FIELDS = [
    "chunk_id",
    "course_id",
    "course_name",
    "lecture_id",
    "lecture_title",
    "source_type",
    "source_file",
    "text",
    "start_time",
    "end_time",
    "page",
]

_STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "also", "am", "an", "and",
    "any", "are", "aren", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "can", "cannot", "could", "did", "do", "does", "doing",
    "don", "down", "during", "each", "either", "else", "even", "every", "example", "examples",
    "few", "first", "for", "from", "further", "get", "gets", "getting", "give", "given",
    "gives", "go", "going", "good", "got", "had", "has", "have", "having", "he", "her",
    "here", "hers", "herself", "him", "himself", "his", "how", "however", "i", "if", "in",
    "into", "is", "isn", "it", "its", "itself", "just", "keep", "know", "known", "lecture",
    "lectures", "let", "lets", "like", "look", "looking", "looks", "made", "make", "makes",
    "making", "many", "may", "me", "might", "more", "most", "much", "must", "my", "myself",
    "need", "needs", "new", "next", "no", "nor", "not", "now", "of", "off", "often", "okay",
    "on", "once", "one", "ones", "only", "or", "other", "others", "ought", "our", "ours",
    "ourselves", "out", "over", "own", "page", "part", "parts", "really", "right", "said",
    "same", "say", "saying", "says", "second", "section", "see", "seeing", "seem", "seen",
    "shall", "she", "should", "show", "shown", "shows", "slide", "slides", "so", "some",
    "something", "still", "such", "take", "taken", "takes", "taking", "talk", "talking",
    "tell", "than", "that", "the", "their", "theirs", "them", "themselves", "then", "there",
    "therefore", "these", "they", "thing", "things", "think", "thinking", "third", "this",
    "those", "though", "three", "through", "thus", "time", "times", "to", "today", "together",
    "too", "topic", "topics", "two", "under", "until", "up", "upon", "us", "use", "used",
    "uses", "using", "very", "want", "wants", "was", "wasn", "way", "ways", "we", "welcome",
    "well", "were", "weren", "what", "when", "where", "whether", "which", "while", "who",
    "whom", "why", "will", "with", "within", "without", "work", "working", "works", "would",
    "you", "your", "yours", "yourself", "yourselves",
}

_TOKEN_PATTERN = re.compile(r"\b[a-zA-Z0-9][a-zA-Z0-9_-]{1,}\b")


def create_chunk_metadata(
    chunk_id: str,
    course_id: str,
    lecture_id: str,
    source_type: str,
    text: str,
    course_name: str = "",
    lecture_title: str = "",
    source_file: str = "",
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    page: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Creates a unified chunk dictionary adhering to the system's metadata schema.

    Args:
        chunk_id: Unique identifier for the chunk.
        course_id: Identifier for the course.
        lecture_id: Identifier for the lecture.
        source_type: Type of source material ('transcript' or 'pdf').
        text: Cleaned text content of the chunk.
        course_name: Full human-readable name of the course.
        lecture_title: Title of the lecture.
        source_file: Filename of origin.
        start_time: Start timestamp in seconds (for transcript chunks).
        end_time: End timestamp in seconds (for transcript chunks).
        page: Page number 1-indexed (for PDF chunks).

    Returns:
        Dict adhering to the unified chunk metadata specification.
    """
    if source_type not in ("transcript", "pdf"):
        raise ValueError(f"Invalid source_type '{source_type}'. Expected 'transcript' or 'pdf'.")

    chunk = {
        "chunk_id": chunk_id,
        "course_id": course_id,
        "course_name": course_name,
        "lecture_id": lecture_id,
        "lecture_title": lecture_title,
        "source_type": source_type,
        "source_file": source_file,
        "text": text,
        "start_time": float(start_time) if start_time is not None else None,
        "end_time": float(end_time) if end_time is not None else None,
        "page": int(page) if page is not None else None,
    }

    validate_chunk(chunk)
    return chunk


def validate_chunk(chunk: Dict[str, Any]) -> bool:
    """
    Validates that a chunk dict contains all required metadata fields and respects type constraints.

    Returns True if valid; raises ValueError if invalid.
    """
    if not isinstance(chunk, dict):
        raise ValueError("Chunk must be a dictionary.")

    for field in REQUIRED_FIELDS:
        if field not in chunk:
            raise ValueError(f"Missing required metadata field: '{field}' in chunk {chunk.get('chunk_id')}")

    for id_field in ("chunk_id", "course_id", "lecture_id"):
        val = chunk.get(id_field)
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"Chunk field '{id_field}' must be a non-empty string.")

    source_type = chunk.get("source_type")
    if source_type == "transcript":
        if chunk.get("start_time") is None:
            raise ValueError(f"Transcript chunk '{chunk.get('chunk_id')}' must have a non-null start_time.")
        if chunk.get("end_time") is None:
            raise ValueError(f"Transcript chunk '{chunk.get('chunk_id')}' must have a non-null end_time.")
        if float(chunk["start_time"]) > float(chunk["end_time"]):
            raise ValueError(
                f"Transcript chunk '{chunk.get('chunk_id')}' has start_time > end_time."
            )
    elif source_type == "pdf":
        if chunk.get("page") is None:
            raise ValueError(f"PDF chunk '{chunk.get('chunk_id')}' must have a non-null page number.")
        if int(chunk["page"]) < 1:
            raise ValueError(f"PDF chunk '{chunk.get('chunk_id')}' must have page >= 1.")
    else:
        raise ValueError(f"Unknown source_type '{source_type}' in chunk '{chunk.get('chunk_id')}'.")

    if not isinstance(chunk.get("text"), str) or not chunk.get("text").strip():
        raise ValueError(f"Chunk '{chunk.get('chunk_id')}' contains empty or non-string text.")

    return True


def _extract_candidate_terms(text: str) -> List[str]:
    """Extracts informative domain unigrams and adjacent technical bigrams from text."""
    raw_tokens = [tok.lower() for tok in _TOKEN_PATTERN.findall(text)]
    filtered = [
        tok for tok in raw_tokens
        if tok not in _STOPWORDS and not tok.isdigit() and len(tok) >= 2
    ]

    terms: List[str] = list(filtered)
    # Add adjacent non-stopword bigrams appearing directly next to each other in raw text
    for i in range(len(raw_tokens) - 1):
        w1, w2 = raw_tokens[i], raw_tokens[i + 1]
        if (
            w1 not in _STOPWORDS
            and w2 not in _STOPWORDS
            and not w1.isdigit()
            and not w2.isdigit()
            and len(w1) >= 2
            and len(w2) >= 2
        ):
            terms.append(f"{w1} {w2}")

    return terms


def derive_lecture_concepts(
    chunks: List[Dict[str, Any]],
    max_units: int = 10,
    keywords_per_unit: int = 6,
) -> List[Dict[str, Any]]:
    """
    Deterministically derives lecture-specific concept units directly from the selected
    lecture's chunks (zero hardcoded or cross-lecture topics).

    Partitions the lecture's chunks into up to `max_units` contiguous topic units and
    extracts salient domain keywords/phrases per unit via TF-IDF weighting.
    """
    valid_chunks = [c for c in chunks if isinstance(c.get("text"), str) and c["text"].strip()]
    if not valid_chunks:
        return []

    num_chunks = len(valid_chunks)
    num_units = min(max_units, num_chunks)

    # Partition chunks evenly across num_units contiguous groups
    unit_groups: List[List[Dict[str, Any]]] = []
    for idx in range(num_units):
        start_i = (idx * num_chunks) // num_units
        end_i = ((idx + 1) * num_chunks) // num_units
        group = valid_chunks[start_i:end_i]
        if group:
            unit_groups.append(group)

    unit_term_counts: List[Counter] = []
    doc_freq: Counter = Counter()

    for group in unit_groups:
        combined_text = " ".join(c["text"] for c in group)
        terms = _extract_candidate_terms(combined_text)
        counts = Counter(terms)
        unit_term_counts.append(counts)
        for unique_term in counts.keys():
            doc_freq[unique_term] += 1

    total_units = len(unit_groups)
    concepts: List[Dict[str, Any]] = []

    for u_idx, (group, counts) in enumerate(zip(unit_groups, unit_term_counts), start=1):
        scored_terms = []
        for term, tf in counts.items():
            idf = 1.0 + math.log((1.0 + total_units) / (1.0 + doc_freq[term]))
            bigram_bonus = 1.25 if " " in term else 1.0
            score = tf * idf * bigram_bonus
            scored_terms.append((score, tf, len(term), term))

        scored_terms.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))

        selected_keywords: List[str] = []
        for _, _, _, term in scored_terms:
            if len(selected_keywords) >= keywords_per_unit:
                break
            # Avoid adding redundant unigram if already represented by a selected bigram and plenty of terms exist
            if term not in selected_keywords:
                selected_keywords.append(term)

        label = " / ".join(selected_keywords[:3]) if selected_keywords else f"Section {u_idx}"
        concepts.append({
            "unit_id": f"U{u_idx:02d}",
            "label": label,
            "keywords": selected_keywords,
            "chunk_ids": [c["chunk_id"] for c in group],
        })

    return concepts


def build_dataset_metadata(
    all_chunks: List[Dict[str, Any]],
    output_path: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generates summary dataset metadata for a lecture's processed chunks,
    including lecture-derived concept units for auditable coverage scoring.

    Args:
        all_chunks: List of chunk metadata dictionaries for the lecture.
        output_path: Optional file path to save the dataset metadata JSON.
        extra_metadata: Optional additional metadata fields (e.g. source hashes).

    Returns:
        Dataset metadata summary dict.
    """
    transcript_chunks = [c for c in all_chunks if c.get("source_type") == "transcript"]
    pdf_chunks = [c for c in all_chunks if c.get("source_type") == "pdf"]

    course_ids = sorted(list(set(c["course_id"] for c in all_chunks if "course_id" in c)))
    lecture_ids = sorted(list(set(c["lecture_id"] for c in all_chunks if "lecture_id" in c)))

    lecture_concepts = derive_lecture_concepts(all_chunks)

    dataset_summary: Dict[str, Any] = {
        "total_chunks": len(all_chunks),
        "total_transcript_chunks": len(transcript_chunks),
        "total_pdf_chunks": len(pdf_chunks),
        "courses": course_ids,
        "lectures": lecture_ids,
        "chunk_ids": [c["chunk_id"] for c in all_chunks],
        "lecture_concepts": lecture_concepts,
    }

    if all_chunks:
        dataset_summary["course_id"] = all_chunks[0].get("course_id", "")
        dataset_summary["course_name"] = all_chunks[0].get("course_name", "")
        dataset_summary["lecture_id"] = all_chunks[0].get("lecture_id", "")
        dataset_summary["lecture_title"] = all_chunks[0].get("lecture_title", "")

    if extra_metadata:
        dataset_summary.update(extra_metadata)

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(dataset_summary, f, indent=2, ensure_ascii=False)

    return dataset_summary
