"""Conservative, extractive knowledge units linked to authoritative evidence."""

import re
from typing import Any, Dict, Iterable, List, Tuple

from .chunker import normalize_text

# A concept is emitted only when its trigger phrase occurs in the evidence.
# Labels are retrieval metadata, never a replacement for the linked source.
CONCEPT_TRIGGERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("Computational thinking", ("computational thinking",)),
    ("Programming practice", ("programming is actually a skill", "practice practice practice", "opportunities to practice")),
    ("Problem solving", ("problem solving",)),
    ("Python programming", ("python programming language", "python programs", "python interpreter")),
    ("Declarative knowledge", ("declarative knowledge",)),
    ("Imperative knowledge", ("imperative knowledge",)),
    ("Algorithms", ("algorithm", "algorithms")),
    ("Flow of control", ("flow of control",)),
    ("Stored-program computer", ("stored program computer",)),
    ("Primitive constructs", ("primitive constructs",)),
    ("Programming language syntax", ("syntax", "syntactically valid")),
    ("Static semantics", ("static semantics",)),
    ("Program semantics", ("semantics: the meaning",)),
    ("Objects and types", ("objects have a type", "objects in memory have types", "type of an object")),
    ("Type conversion", ("type conversion", "casts the int", "implicit casts")),
    ("Expressions", ("expressions", "expression has a value")),
    ("Variables", ("variables", "variable names")),
    ("Assignment", ("assignment binds", "equal sign is an assignment")),
    ("Variable binding", ("bind a value", "binding variables")),
)


def _sentences(text: str) -> List[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", normalize_text(text)) if sentence.strip()]


def _extractive_statement(text: str, triggers: Tuple[str, ...]) -> str:
    """Return source sentences containing a trigger; never generate new prose."""
    matches = [sentence for sentence in _sentences(text) if any(trigger in sentence.lower() for trigger in triggers)]
    # Keep one contiguous source sentence. Joining excerpts can accidentally
    # create wording that is not itself a contiguous span of the evidence.
    return matches[0] if matches else normalize_text(text)


def extract_knowledge_units(evidence_documents: Iterable[Dict[str, Any]], lecture_id: str) -> List[Dict[str, Any]]:
    """Create source-bounded concept records in deterministic evidence order."""
    units: List[Dict[str, Any]] = []
    seen = set()
    for document in evidence_documents:
        text = normalize_text(str(document["original_text"]))
        lowered = text.lower()
        for concept, triggers in CONCEPT_TRIGGERS:
            if not any(trigger in lowered for trigger in triggers):
                continue
            # One concept/unit per evidence chunk prevents an unsupported merge.
            key = (document["chunk_id"], concept)
            if key in seen:
                continue
            seen.add(key)
            evidence = {"source_type": document["source_type"], "source_file": document["source_file"],
                        "start": document["start"], "end": document["end"], "page": document["page"]}
            units.append({
                "knowledge_id": f"{lecture_id}_k{len(units) + 1:04d}",
                "lecture_id": lecture_id,
                "document_type": "knowledge",
                "concept": concept,
                "teaching_statement": _extractive_statement(text, triggers),
                "evidence_chunk_ids": [document["chunk_id"]],
                "evidence": [evidence],
                "source_type": document["source_type"],
            })
    return units
