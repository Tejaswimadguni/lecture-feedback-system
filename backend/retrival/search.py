import json
import sys
from pathlib import Path

# Ensure Windows terminal doesn't crash on unicode PDF/PPT bullet symbols
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from embedding import generate_embedding
from vector_store import load_faiss_index



# --------------------------------------------------
# Paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

FAISS_FILE = (
    PROJECT_ROOT
    / "data"
    / "vector_store"
    / "lecture_index.faiss"
)

MAPPING_FILE = (
    PROJECT_ROOT
    / "data"
    / "vector_store"
    / "chunk_mapping.json"
)


# --------------------------------------------------
# Load chunk mapping
# --------------------------------------------------

def load_mapping():

    with open(
        MAPPING_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


# --------------------------------------------------
# Search
# --------------------------------------------------

def search(query, top_k=5):

    # Load FAISS
    index = load_faiss_index(
        FAISS_FILE
    )

    # Load mapping
    mapping = load_mapping()

    # Convert query into embedding
    query_embedding = generate_embedding(
        query
    )

    # Search FAISS
    scores, vector_ids = index.search(
        query_embedding,
        top_k
    )

    results = []

    for score, vector_id in zip(
        scores[0],
        vector_ids[0]
    ):

        # FAISS can return -1 if there isn't a result
        if vector_id == -1:
            continue

        chunk = mapping[vector_id]

        results.append({
            "score": float(score),
            "vector_id": int(vector_id),
            "chunk_id": chunk["chunk_id"],
            "source_type": chunk["source_type"],
            "source_file": chunk["source_file"],
            "page": chunk.get("page"),
            "start_time": chunk.get("start_time"),
            "end_time": chunk.get("end_time"),
            "text": chunk["text"]
        })

    return results


# --------------------------------------------------
# Test
# --------------------------------------------------

if __name__ == "__main__":

    query = "What is declarative knowledge?"

    print("\n===================================")
    print("SEMANTIC SEARCH")
    print("===================================")

    print(f"\nQuery: {query}")

    results = search(
        query,
        top_k=5
    )

    for i, result in enumerate(
        results,
        start=1
    ):

        print("\n-----------------------------------")
        print(f"Result {i}")
        print("-----------------------------------")

        print(
            f"Similarity: {result['score']:.4f}"
        )

        print(
            f"Vector ID: {result['vector_id']}"
        )

        print(
            f"Chunk ID: {result['chunk_id']}"
        )

        print(
            f"Source: {result['source_type']}"
        )

        if result["page"] is not None:

            print(
                f"Page: {result['page']}"
            )

        if result["start_time"] is not None:

            print(
                f"Time: "
                f"{result['start_time']:.2f}"
                f" - "
                f"{result['end_time']:.2f}"
            )

        print(
            f"Text: {result['text']}"
        )