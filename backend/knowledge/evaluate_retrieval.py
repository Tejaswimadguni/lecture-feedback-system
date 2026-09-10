"""Detailed source-grounded retrieval diagnostics for a lecture knowledge layer."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from retrival.embedding import Embedder
from retrival.vector_store import VectorStore

# These expected evidence IDs were selected by inspecting the Lecture 1 source
# evidence, not by observing retrieval ranks. They are evaluation ground truth.
EVALUATION_SET = [
    {"query": "What did the professor say about computational thinking?", "concept": "Computational thinking", "source_type": "audio", "evidence_ids": ["lecture01_audio_0005"]},
    {"query": "How is programming practice presented in the course?", "concept": "Programming practice", "source_type": "audio", "evidence_ids": ["lecture01_audio_0003"]},
    {"query": "What is declarative knowledge?", "concept": "Declarative knowledge", "source_type": "audio", "evidence_ids": ["lecture01_audio_0007"]},
    {"query": "What is imperative knowledge?", "concept": "Imperative knowledge", "source_type": "audio", "evidence_ids": ["lecture01_audio_0007"]},
    {"query": "What is the square root algorithm?", "concept": "Algorithms", "source_type": "pdf", "evidence_ids": ["lecture01_pdf_page_8_chunk_0008"]},
    {"query": "What is flow of control?", "concept": "Flow of control", "source_type": "pdf", "evidence_ids": ["lecture01_pdf_page_11_chunk_0011"]},
    {"query": "What is a stored-program computer?", "concept": "Stored-program computer", "source_type": "pdf", "evidence_ids": ["lecture01_pdf_page_15_chunk_0015"]},
    {"query": "What are primitive constructs?", "concept": "Programming language syntax", "source_type": "pdf", "evidence_ids": ["lecture01_pdf_page_26_chunk_0026"]},
    {"query": "What is static semantics?", "concept": "Static semantics", "source_type": "pdf", "evidence_ids": ["lecture01_pdf_page_28_chunk_0028"]},
    {"query": "How are Python programs evaluated?", "concept": "Python programming", "source_type": "pdf", "evidence_ids": ["lecture01_pdf_page_31_chunk_0031"]},
    {"query": "What does an object type determine?", "concept": "Objects and types", "source_type": "pdf", "evidence_ids": ["lecture01_pdf_page_33_chunk_0033"]},
    {"query": "How does type conversion work?", "concept": "Type conversion", "source_type": "pdf", "evidence_ids": ["lecture01_pdf_page_38_chunk_0038"]},
    {"query": "What is an expression?", "concept": "Expressions", "source_type": "pdf", "evidence_ids": ["lecture01_pdf_page_40_chunk_0040"]},
    {"query": "What are variables in programming?", "concept": "Variables", "source_type": "pdf", "evidence_ids": ["lecture01_pdf_page_47_chunk_0047"]},
    {"query": "What does assignment do?", "concept": "Assignment", "source_type": "pdf", "evidence_ids": ["lecture01_pdf_page_48_chunk_0048"]},
    {"query": "Why use names for expression values?", "concept": "Variables", "source_type": "pdf", "evidence_ids": ["lecture01_pdf_page_50_chunk_0050"]},
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate knowledge retrieval with source-grounded queries.")
    parser.add_argument("--lecture-id", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    store_dir = ROOT / "data" / "processed" / "vector_store" / args.lecture_id / "knowledge"
    embedder, store = Embedder(), VectorStore.load(store_dir)
    hits, reciprocal_ranks, rows = {1: 0, 3: 0, 5: 0}, [], []
    for test in EVALUATION_SET:
        results = store.search(embedder.encode([test["query"]])[0], max(args.top_k, 5))
        rank = next((index for index, item in enumerate(results, 1) if set(item["evidence_chunk_ids"]) & set(test["evidence_ids"])), None)
        for cutoff in hits:
            hits[cutoff] += bool(rank and rank <= cutoff)
        reciprocal_ranks.append(1 / rank if rank else 0)
        rows.append({**test, "pass": bool(rank and rank <= args.top_k), "matching_rank": rank,
                     "results": [{"rank": index, "score": item["score"], "document_type": item["document_type"], "concept": item["concept"], "source_type": item["source_type"], "evidence_chunk_ids": item["evidence_chunk_ids"], "evidence": item["evidence"], "text_excerpt": item["teaching_statement"][:240]} for index, item in enumerate(results, 1)]})
    total = len(EVALUATION_SET)
    report = {"lecture_id": args.lecture_id, "query_count": total, "top_1_recall": hits[1] / total, "top_3_recall": hits[3] / total, "top_5_recall": hits[5] / total, "mrr": sum(reciprocal_ranks) / total, "results": rows}
    output = ROOT / "data" / "processed" / "knowledge_base" / args.lecture_id / "retrieval_report.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for row in rows:
        print(f"\nQUERY: {row['query']}\nExpected: {row['concept']} ({row['source_type']})\nPASS: {row['pass']}")
        for result in row["results"]:
            print(f"  {result['rank']}. {result['score']:.3f} | {result['document_type']} | {result['concept']} | {result['source_type']} | {result['evidence_chunk_ids']}\n     {result['text_excerpt']}")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2))


if __name__ == "__main__":
    main()
