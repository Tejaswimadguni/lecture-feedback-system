import os
import sys

# Ensure project root is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.run_lecture_pipeline import main

if __name__ == "__main__":
    main()
