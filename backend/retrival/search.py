import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Ensure Windows terminal doesn't crash on unicode PDF/PPT bullet symbols
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.paths import validate_identifier
from backend.retrival.embedding import generate_embedding
from backend.retrival.vector_store import validate_and_load_knowledge_base


def search(
    query: str,
    course_id: str,
    lecture_id: str,
    top_k: int = 5,
    source_type: Optional[str] = None,
    data_root: Optional[Union[str, Path]] = None,
    loaded_kb: Optional[Tuple[Any, List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """
    Executes semantic similarity search strictly against the specified lecture's isolated
    knowledge base at:
        {data_root}/lectures/{course_id}/{lecture_id}/knowledge_base/

    Never searches other lectures or any global index.
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")

    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query must be a non-empty string.")
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    if source_type is not None and source_type not in ("transcript", "pdf"):
        raise ValueError(f"Invalid source_type filter '{source_type}'. Expected 'transcript' or 'pdf'.")

    if loaded_kb is not None:
        index, mapping = loaded_kb
        if index.ntotal != len(mapping) or len(mapping) == 0:
            raise ValueError("Provided loaded_kb is empty or has mismatched vector/mapping counts.")
        for entry in mapping:
            if entry.get("course_id") != valid_course_id or entry.get("lecture_id") != valid_lecture_id:
                raise ValueError(
                    f"Loaded knowledge base mismatch: expected {valid_course_id}/{valid_lecture_id}, "
                    f"found {entry.get('course_id')}/{entry.get('lecture_id')}."
                )
    else:
        index, mapping = validate_and_load_knowledge_base(
            course_id=valid_course_id,
            lecture_id=valid_lecture_id,
            data_root=data_root,
        )

    query_embedding = generate_embedding(query)

    # Search extra candidates when source_type filter is active so top_k filtered items can be returned
    search_k = len(mapping) if source_type is not None else min(top_k, len(mapping))
    scores, vector_ids = index.search(query_embedding, search_k)

    results: List[Dict[str, Any]] = []
    for score, vector_id in zip(scores[0], vector_ids[0]):
        vid = int(vector_id)
        if vid < 0:
            continue
        if vid >= len(mapping):
            raise ValueError(
                f"FAISS returned out-of-bounds vector_id={vid} for mapping of size {len(mapping)}."
            )

        chunk = mapping[vid]
        if chunk.get("course_id") != valid_course_id or chunk.get("lecture_id") != valid_lecture_id:
            raise ValueError(
                f"Cross-lecture chunk detected during retrieval: {chunk.get('chunk_id')}"
            )

        if source_type is not None and chunk.get("source_type") != source_type:
            continue

        results.append({
            "score": float(score),
            "vector_id": vid,
            "course_id": chunk["course_id"],
            "lecture_id": chunk["lecture_id"],
            "chunk_id": chunk["chunk_id"],
            "source_type": chunk["source_type"],
            "source_file": chunk.get("source_file", ""),
            "page": chunk.get("page"),
            "start_time": chunk.get("start_time"),
            "end_time": chunk.get("end_time"),
            "text": chunk["text"],
        })

        if len(results) >= top_k:
            break

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run semantic search strictly within a specified lecture's knowledge base."
    )
    parser.add_argument("--course-id", required=True, help="Explicit course identifier.")
    parser.add_argument("--lecture-id", required=True, help="Explicit lecture identifier.")
    parser.add_argument("--query", required=True, help="Search query text.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of top results to return (default: 5).")
    parser.add_argument(
        "--source-type",
        choices=["transcript", "pdf"],
        default=None,
        help="Optional filter by source type.",
    )
    parser.add_argument("--data-root", default=None, help="Optional custom data root directory.")

    args = parser.parse_args()

    try:
        results = search(
            query=args.query,
            course_id=args.course_id,
            lecture_id=args.lecture_id,
            top_k=args.top_k,
            source_type=args.source_type,
            data_root=args.data_root,
        )

        print("\n===================================")
        print(f"SEMANTIC SEARCH ({args.course_id} / {args.lecture_id})")
        print("===================================")
        print(f"\nQuery: {args.query}")

        for i, result in enumerate(results, start=1):
            print("\n-----------------------------------")
            print(f"Result {i}")
            print("-----------------------------------")
            print(f"Similarity : {result['score']:.4f}")
            print(f"Vector ID  : {result['vector_id']}")
            print(f"Course ID  : {result['course_id']}")
            print(f"Lecture ID : {result['lecture_id']}")
            print(f"Chunk ID   : {result['chunk_id']}")
            print(f"Source     : {result['source_type']} ({result['source_file']})")
            if result["page"] is not None:
                print(f"Page       : {result['page']}")
            if result["start_time"] is not None:
                print(f"Time       : {result['start_time']:.2f} - {result['end_time']:.2f}")
            print(f"Text       : {result['text']}")
    except Exception as e:
        print(f"Error during semantic search: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
