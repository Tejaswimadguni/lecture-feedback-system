import os
import sys
import tempfile
from pathlib import Path

# Ensure project root is on sys.path when script is executed directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.processing.metadata import create_chunk_metadata
from backend.retrival.build_index import build_lecture_index
from backend.retrival.embedding import EmbeddingModel, generate_embeddings
from backend.retrival.search import search
from backend.retrival.vector_store import validate_and_load_knowledge_base


def test_embedding_model_shape_and_similarity():
    embedder = EmbeddingModel()
    texts = [
        "First normal form requires atomic attribute values in relational tables",
        "Every column in a 1NF table must hold atomic indivisible values",
        "Photosynthesis converts sunlight into chemical energy in plant leaves",
    ]

    vecs = embedder.encode(texts, normalize=True)
    assert vecs.shape == (3, 384)

    raw_vecs = generate_embeddings(texts)
    assert raw_vecs.shape == (3, 384)

    sim_related = embedder.similarity(texts[0], texts[1])
    sim_unrelated = embedder.similarity(texts[0], texts[2])

    assert sim_related > sim_unrelated
    assert 0.0 <= sim_related <= 1.0


def test_vector_store_build_search_and_filter():
    with tempfile.TemporaryDirectory() as tmp_dir:
        chunks = [
            create_chunk_metadata(
                chunk_id="DBMS_DBMS_lect1_T001",
                course_id="DBMS",
                lecture_id="DBMS_lect1",
                course_name="Database Management Systems",
                lecture_title="Normalization",
                source_type="transcript",
                source_file="normalization.mp3",
                text="Today we discuss database normalization and eliminating update anomalies.",
                start_time=0.0,
                end_time=12.5,
                page=None,
            ),
            create_chunk_metadata(
                chunk_id="DBMS_DBMS_lect1_P04_C01",
                course_id="DBMS",
                lecture_id="DBMS_lect1",
                course_name="Database Management Systems",
                lecture_title="Normalization",
                source_type="pdf",
                source_file="normalization.pdf",
                text="First Normal Form (1NF) requires atomic values and no repeating groups.",
                start_time=None,
                end_time=None,
                page=4,
            ),
        ]

        summary = build_lecture_index(
            course_id="DBMS",
            lecture_id="DBMS_lect1",
            chunks=chunks,
            data_root=tmp_dir,
        )
        assert summary["total_vectors"] == 2

        index, mapping = validate_and_load_knowledge_base(
            course_id="DBMS",
            lecture_id="DBMS_lect1",
            data_root=tmp_dir,
        )
        assert index.ntotal == len(mapping) == 2

        # Unfiltered search within DBMS / DBMS_lect1
        results = search(
            query="What does First Normal Form require?",
            course_id="DBMS",
            lecture_id="DBMS_lect1",
            top_k=2,
            data_root=tmp_dir,
        )
        assert len(results) == 2
        assert all(r["course_id"] == "DBMS" and r["lecture_id"] == "DBMS_lect1" for r in results)

        # Filtered search by transcript
        t_results = search(
            query="normalization anomalies",
            course_id="DBMS",
            lecture_id="DBMS_lect1",
            top_k=5,
            source_type="transcript",
            data_root=tmp_dir,
        )
        assert len(t_results) == 1
        assert t_results[0]["source_type"] == "transcript"
        assert t_results[0]["start_time"] == 0.0
        assert t_results[0]["end_time"] == 12.5

        # Filtered search by pdf
        p_results = search(
            query="1NF atomic values",
            course_id="DBMS",
            lecture_id="DBMS_lect1",
            top_k=5,
            source_type="pdf",
            data_root=tmp_dir,
        )
        assert len(p_results) == 1
        assert p_results[0]["source_type"] == "pdf"
        assert p_results[0]["page"] == 4


def test_semantic_search_end_to_end():
    with tempfile.TemporaryDirectory() as tmp_dir:
        chunks = [
            create_chunk_metadata(
                chunk_id=f"OS_OS_lect1_P0{i}_C01",
                course_id="OS",
                lecture_id="OS_lect1",
                course_name="Operating Systems",
                lecture_title="CPU Scheduling",
                source_type="pdf",
                source_file="scheduling.pdf",
                text=txt,
                page=i,
            )
            for i, txt in enumerate(
                [
                    "Round Robin scheduling assigns a fixed time quantum to each ready process.",
                    "Shortest Job First minimizes average waiting time for a given set of processes.",
                    "Multilevel Feedback Queue dynamically adjusts process priority based on CPU bursts.",
                ],
                start=1,
            )
        ]

        build_lecture_index(
            course_id="OS",
            lecture_id="OS_lect1",
            chunks=chunks,
            data_root=tmp_dir,
        )

        hits = search(
            query="Which algorithm uses a fixed time quantum?",
            course_id="OS",
            lecture_id="OS_lect1",
            top_k=3,
            data_root=tmp_dir,
        )

        assert len(hits) == 3
        assert "Round Robin" in hits[0]["text"]
        for hit in hits:
            assert hit["course_id"] == "OS"
            assert hit["lecture_id"] == "OS_lect1"
            assert "chunk_id" in hit
            assert "source_type" in hit
            assert "source_file" in hit
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
