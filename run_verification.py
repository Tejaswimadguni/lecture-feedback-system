import os
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.verification.pipeline import run_verification_pipeline

if __name__ == "__main__":
    run_verification_pipeline()
