import os
import sys

# Ensure backend root is on sys.path when script is executed directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.retrieval.embedding import EmbeddingModel
from backend.retrieval.vector_store import VectorStore
from backend.retrieval.search import SemanticSearch


def test_embedding_model_shape_and_similarity():
    embedder = EmbeddingModel()
    texts = [
        "Python variables store values in memory",
        "A variable refers to a value in memory",
        "The sun is shining brightly today"
    ]

    vecs = embedder.encode(texts, normalize=True)

    assert vecs.shape == (3, 384)

    sim_related = embedder.similarity(texts[0], texts[1])
    sim_unrelated = embedder.similarity(texts[0], texts[2])

    assert sim_related > sim_unrelated
    assert 0.0 <= sim_related <= 1.0


def test_vector_store_build_search_and_filter():
    embedder = EmbeddingModel()
    store = VectorStore(dimension=384)

    chunks = [
        {
            "chunk_id": "MIT_6_100L_lec01_T001",
            "course_id": "MIT_6_100L",
            "lecture_id": "lec01",
            "source_type": "transcript",
            "text": "Today we are going to discuss variables.",
            "start_time": 0.0,
            "end_time": 12.5,
            "page": None
        },
        {
            "chunk_id": "MIT_6_100L_lec01_P04_C01",
            "course_id": "MIT_6_100L",
            "lecture_id": "lec01",
            "source_type": "pdf",
            "text": "A variable is a name that refers to a value.",
            "start_time": None,
            "end_time": None,
            "page": 4
        }
    ]

    indexed_cnt = store.build_index(chunks, embedder)
    assert indexed_cnt == 2

    # Query search without filter
    query_vec = embedder.encode("variable definition", normalize=True)
    results = store.search(query_vec, top_k=2)

    assert len(results) == 2
    assert "score" in results[0]

    # Filter search by transcript
    t_results = store.search(query_vec, top_k=5, source_type="transcript")
    assert len(t_results) == 1
    assert t_results[0]["source_type"] == "transcript"
    assert t_results[0]["start_time"] is not None

    # Filter search by pdf
    p_results = store.search(query_vec, top_k=5, source_type="pdf")
    assert len(p_results) == 1
    assert p_results[0]["source_type"] == "pdf"
    assert p_results[0]["page"] == 4


def test_semantic_search_end_to_end():
    search_engine = SemanticSearch()
    count = search_engine.index_processed_dataset()

    assert count > 0

    hits = search_engine.search("What is a variable?", top_k=3)

    assert len(hits) == 3
    for hit in hits:
        assert "chunk_id" in hit
        assert "source_type" in hit
        assert "score" in hit
        assert "text" in hit


if __name__ == "__main__":
    print("Running test_retrieval.py...")
    test_embedding_model_shape_and_similarity()
    print("[PASSED] test_embedding_model_shape_and_similarity")
    test_vector_store_build_search_and_filter()
    print("[PASSED] test_vector_store_build_search_and_filter")
    test_semantic_search_end_to_end()
    print("[PASSED] test_semantic_search_end_to_end")
    print("All retrieval tests passed!")
