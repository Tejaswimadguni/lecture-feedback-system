import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.test_transcript_processing import (
    test_clean_transcript_removes_filler_words_and_preserves_timestamps,
    test_chunk_transcript_timestamps_and_metadata,
)
from tests.test_pdf_processing import (
    test_clean_pdf_removes_headers_footers_preserves_equations,
    test_chunk_pdf_page_aware_and_metadata,
)
from tests.test_metadata import (
    test_transcript_chunk_metadata_schema,
    test_pdf_chunk_metadata_schema,
    test_invalid_chunk_metadata_raises,
    test_build_dataset_metadata,
)


def run_all_tests():
    test_functions = [
        ("test_clean_transcript_removes_filler_words_and_preserves_timestamps", test_clean_transcript_removes_filler_words_and_preserves_timestamps),
        ("test_chunk_transcript_timestamps_and_metadata", test_chunk_transcript_timestamps_and_metadata),
        ("test_clean_pdf_removes_headers_footers_preserves_equations", test_clean_pdf_removes_headers_footers_preserves_equations),
        ("test_chunk_pdf_page_aware_and_metadata", test_chunk_pdf_page_aware_and_metadata),
        ("test_transcript_chunk_metadata_schema", test_transcript_chunk_metadata_schema),
        ("test_pdf_chunk_metadata_schema", test_pdf_chunk_metadata_schema),
        ("test_invalid_chunk_metadata_raises", test_invalid_chunk_metadata_raises),
        ("test_build_dataset_metadata", test_build_dataset_metadata),
    ]

    passed = 0
    failed = 0

    print("=========================================")
    print(" Running Section 2 Tests ")
    print("=========================================")

    for name, func in test_functions:
        try:
            func()
            print(f"[PASSED] {name}")
            passed += 1
        except Exception as e:
            print(f"[FAILED] {name}: {e}")
            failed += 1

    print("=========================================")
    print(f"Results: {passed} passed, {failed} failed.")
    print("=========================================")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
