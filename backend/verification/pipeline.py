import os
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from .claims import main as run_claims_extraction
    from .retrieve_evidence import main as run_evidence_retrieval
    from .evaluvator import main as run_claim_evaluation
    from .scorer import main as run_student_scoring
except ImportError:
    from claims import main as run_claims_extraction
    from retrieve_evidence import main as run_evidence_retrieval
    from evaluvator import main as run_claim_evaluation
    from scorer import main as run_student_scoring


def run_verification_pipeline():
    """
    Master pipeline runner for student feedback claim verification & evaluation.
    Executes sequentially:
      1. Claim Extraction (Student Feedback -> Factual Claims)
      2. Evidence Retrieval (Claims -> Top-K FAISS Lecture Evidence Chunks)
      3. Claim Evaluation (LLM Verification: SUPPORTED / PARTIALLY_SUPPORTED / NOT_SUPPORTED)
      4. Student Scoring (Factual Accuracy & Quality Scores)
    """
    print("\n=========================================================", flush=True)
    print("      STUDENT FEEDBACK VERIFICATION PIPELINE           ", flush=True)
    print("=========================================================\n", flush=True)

    print("[STEP 1/4] Extracting student factual claims...", flush=True)
    run_claims_extraction()

    # Ensure FAISS index exists before retrieval
    faiss_file = PROJECT_ROOT / "data" / "vector_store" / "lecture_index.faiss"
    if not faiss_file.exists():
        print("\n[PRE-CHECK] FAISS index missing. Building vector index now...", flush=True)
        try:
            from backend.retrival.build_index import main as build_index_main
        except ImportError:
            from retrival.build_index import main as build_index_main
        build_index_main()

    print("\n[STEP 2/4] Retrieving lecture evidence from FAISS vector index...", flush=True)
    run_evidence_retrieval()

    print("\n[STEP 3/4] Evaluating claims against retrieved evidence via LLM...", flush=True)
    run_claim_evaluation()

    print("\n[STEP 4/4] Computing final verification scores & quality metrics...", flush=True)
    run_student_scoring()

    print("\n=========================================================", flush=True)
    print(" Verification Pipeline execution complete!               ", flush=True)
    print("=========================================================\n", flush=True)


if __name__ == "__main__":
    run_verification_pipeline()
