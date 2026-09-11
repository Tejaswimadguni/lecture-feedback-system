import os
import sys

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from backend.processing.pipeline import run_section2_pipeline
from backend.retrieval.search import SemanticSearch
from tests.run_tests import run_all_tests


def main():
    print("=========================================================")
    print("      LECTURE FEEDBACK SYSTEM — MASTER PIPELINE         ")
    print("=========================================================")

    # Step 1: Execute Section 2 — Cleaning -> Chunking -> Metadata
    print("\n[STEP 1/3] Running Data Processing (Cleaning -> Chunking -> Metadata)...")
    dataset_summary = run_section2_pipeline()
    print(f"-> Successfully processed dataset. Total chunks: {dataset_summary.get('total_chunks')}")

    # Step 2: Execute Section 3 — Embeddings + FAISS Vector Store Build
    print("\n[STEP 2/3] Building SentenceTransformer Embeddings & FAISS Vector Index...")
    search_engine = SemanticSearch()
    total_indexed = search_engine.index_processed_dataset()
    print(f"-> Successfully indexed {total_indexed} chunks into FAISS vector store.")

    # Step 3: Run Full Test Suite
    print("\n[STEP 3/3] Executing Automated Test Suite...")
    run_all_tests()

    print("\n=========================================================")
    print(" Pipeline execution complete! All systems operational.  ")
    print("=========================================================")


if __name__ == "__main__":
    main()
