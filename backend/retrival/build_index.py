import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.paths import get_lecture_paths, validate_identifier
from backend.processing.metadata import validate_chunk
from backend.retrival.embedding import generate_embeddings
from backend.retrival.vector_store import create_faiss_index, save_faiss_index


def load_chunks_file(file_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Loads a JSON chunk list file and validates its top-level structure."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Chunks file not found: {p}")

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("chunks"), list):
        return data["chunks"]

    raise ValueError(f"Unexpected JSON structure in chunks file: {p}")


def build_lecture_index(
    course_id: str,
    lecture_id: str,
    chunks: Optional[List[Dict[str, Any]]] = None,
    data_root: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Builds a completely independent FAISS index, embeddings matrix, and chunk mapping
    strictly for {course_id}/{lecture_id} inside:
        {data_root}/lectures/{course_id}/{lecture_id}/knowledge_base/

    Replaces any prior knowledge base for this specific lecture without touching
    any other lecture's files.
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")
    lpaths = get_lecture_paths(valid_course_id, valid_lecture_id, data_root=data_root)

    if chunks is None:
        loaded_chunks: List[Dict[str, Any]] = []
        if lpaths.transcript_chunks.exists():
            loaded_chunks.extend(load_chunks_file(lpaths.transcript_chunks))
        if lpaths.pdf_chunks.exists():
            loaded_chunks.extend(load_chunks_file(lpaths.pdf_chunks))
        if not loaded_chunks:
            raise FileNotFoundError(
                f"No processed chunk files found for {valid_course_id}/{valid_lecture_id} in "
                f"{lpaths.processed_dir}. Expected transcript_chunks.json and/or pdf_chunks.json."
            )
        target_chunks = loaded_chunks
    else:
        target_chunks = list(chunks)

    if not target_chunks:
        raise ValueError(
            f"Cannot build knowledge base for {valid_course_id}/{valid_lecture_id}: chunk list is empty."
        )

    valid_chunks: List[Dict[str, Any]] = []
    texts: List[str] = []

    for chunk in target_chunks:
        validate_chunk(chunk)
        if chunk.get("course_id") != valid_course_id or chunk.get("lecture_id") != valid_lecture_id:
            raise ValueError(
                f"Chunk '{chunk.get('chunk_id')}' belongs to "
                f"{chunk.get('course_id')}/{chunk.get('lecture_id')}, "
                f"cannot index into {valid_course_id}/{valid_lecture_id}."
            )
        text = chunk["text"].strip()
        texts.append(text)
        valid_chunks.append(chunk)

    embeddings = generate_embeddings(texts)
    if embeddings.shape[0] != len(valid_chunks):
        raise RuntimeError(
            f"Generated {embeddings.shape[0]} embeddings for {len(valid_chunks)} chunks."
        )

    faiss_index = create_faiss_index(embeddings)
    lpaths.knowledge_base_dir.mkdir(parents=True, exist_ok=True)

    # Save brand-new independent FAISS index and embeddings for this lecture
    save_faiss_index(faiss_index, lpaths.faiss_index)
    np.save(str(lpaths.embeddings), embeddings)

    mapping: List[Dict[str, Any]] = []
    for vector_id, chunk in enumerate(valid_chunks):
        mapping.append({
            "vector_id": vector_id,
            "chunk_id": chunk["chunk_id"],
            "course_id": valid_course_id,
            "course_name": chunk.get("course_name", ""),
            "lecture_id": valid_lecture_id,
            "lecture_title": chunk.get("lecture_title", ""),
            "source_type": chunk["source_type"],
            "source_file": chunk.get("source_file", ""),
            "page": chunk.get("page"),
            "start_time": chunk.get("start_time"),
            "end_time": chunk.get("end_time"),
            "text": chunk["text"],
        })

    with open(lpaths.chunk_mapping, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)

    return {
        "course_id": valid_course_id,
        "lecture_id": valid_lecture_id,
        "total_vectors": int(faiss_index.ntotal),
        "dimension": int(faiss_index.d),
        "faiss_index_path": str(lpaths.faiss_index),
        "embeddings_path": str(lpaths.embeddings),
        "chunk_mapping_path": str(lpaths.chunk_mapping),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an isolated lecture FAISS knowledge base from processed lecture chunks."
    )
    parser.add_argument("--course-id", required=True, help="Explicit course identifier.")
    parser.add_argument("--lecture-id", required=True, help="Explicit lecture identifier.")
    parser.add_argument("--data-root", default=None, help="Optional custom data root directory.")

    args = parser.parse_args()

    try:
        summary = build_lecture_index(
            course_id=args.course_id,
            lecture_id=args.lecture_id,
            data_root=args.data_root,
        )
        print("\n===================================")
        print("LECTURE KNOWLEDGE BASE BUILT")
        print("===================================")
        print(f"Course ID   : {summary['course_id']}")
        print(f"Lecture ID  : {summary['lecture_id']}")
        print(f"Vectors     : {summary['total_vectors']} (dim={summary['dimension']})")
        print(f"FAISS Index : {summary['faiss_index_path']}")
        print(f"Embeddings  : {summary['embeddings_path']}")
        print(f"Mapping     : {summary['chunk_mapping_path']}")
    except Exception as e:
        print(f"Error building lecture index: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
