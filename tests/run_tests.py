import os
import sys

# Ensure project root is on sys.path
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
from tests.test_retrieval import (
    test_embedding_model_shape_and_similarity,
    test_vector_store_build_search_and_filter,
    test_semantic_search_end_to_end,
)
from tests.test_lecture_isolation_and_verification import (
    test_1_2_3_4_separate_directories_kbs_and_reprocessing_isolation,
    test_5_6_strict_retrieval_cross_lecture_isolation,
    test_7_8_11_dynamic_verification_student_directories_custom_csv_and_scoring,
    test_9_cli_requires_explicit_arguments_no_silent_defaults,
    test_10_comprehensive_validation_and_error_handling,
    test_cache_reuse_only_when_identity_and_config_match,
)
from tests.test_api_and_e2e_workflow import (
    test_e2e_workflow_tests_1_through_8_and_persistence,
    test_9_api_validation_error_handling_and_safe_deletion,
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
        ("test_embedding_model_shape_and_similarity", test_embedding_model_shape_and_similarity),
        ("test_vector_store_build_search_and_filter", test_vector_store_build_search_and_filter),
        ("test_semantic_search_end_to_end", test_semantic_search_end_to_end),
        ("test_1_2_3_4_separate_directories_kbs_and_reprocessing_isolation", test_1_2_3_4_separate_directories_kbs_and_reprocessing_isolation),
        ("test_5_6_strict_retrieval_cross_lecture_isolation", test_5_6_strict_retrieval_cross_lecture_isolation),
        ("test_7_8_11_dynamic_verification_student_directories_custom_csv_and_scoring", test_7_8_11_dynamic_verification_student_directories_custom_csv_and_scoring),
        ("test_9_cli_requires_explicit_arguments_no_silent_defaults", test_9_cli_requires_explicit_arguments_no_silent_defaults),
        ("test_10_comprehensive_validation_and_error_handling", test_10_comprehensive_validation_and_error_handling),
        ("test_cache_reuse_only_when_identity_and_config_match", test_cache_reuse_only_when_identity_and_config_match),
        ("test_e2e_workflow_tests_1_through_8_and_persistence", test_e2e_workflow_tests_1_through_8_and_persistence),
        ("test_9_api_validation_error_handling_and_safe_deletion", test_9_api_validation_error_handling_and_safe_deletion),
    ]

    passed = 0
    failed = 0

    print("=========================================")
    print(" Running Complete Automated Test Suite   ")
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
