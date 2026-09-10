"""Command-line semantic retrieval over a lecture-specific vector store."""

import argparse
from pathlib import Path

from embedding import Embedder
from vector_store import VectorStore


def search(query: str, store_dir: Path, top_k: int = 5):
    embedder = Embedder()
    store = VectorStore.load(store_dir)
    return store.search(embedder.encode([query])[0], top_k)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search a lecture teaching knowledge base.")
    parser.add_argument("query")
    parser.add_argument("--lecture-id", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--document-type", choices=("knowledge", "evidence"), default="knowledge")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    store_dir = root / "data" / "processed" / "vector_store" / args.lecture_id
    if args.document_type == "knowledge":
        store_dir /= "knowledge"
    results = search(args.query, store_dir, args.top_k)
    for result in results:
        if result.get("document_type") == "knowledge":
            print(f"{result['score']:.3f} | knowledge | {result['concept']} | evidence: {result['evidence_chunk_ids']}\n{result['teaching_statement']}\n")
        else:
            location = f"{result['start']:.2f}-{result['end']:.2f}s" if result["source_type"] == "audio" else f"page {result['page']}"
            print(f"{result['score']:.3f} | evidence | {result['source_type']} | {result['lecture_id']} | {location}\n{result['knowledge_text']}\n")


if __name__ == "__main__":
    main()
