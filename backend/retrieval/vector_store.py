import os
import json
import numpy as np
from typing import List, Dict, Any, Optional

try:
    import faiss
except ImportError:
    faiss = None


class VectorStore:
    """
    FAISS-backed vector store using IndexFlatIP for cosine similarity search over L2-normalized vectors.
    Maps 0-indexed vector positions to complete chunk metadata objects.
    """

    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.index = None
        self.metadata_map: Dict[int, Dict[str, Any]] = {}
        self._init_index()

    def _init_index(self):
        if faiss is not None:
            self.index = faiss.IndexFlatIP(self.dimension)

    def build_index(self, chunks: List[Dict[str, Any]], embedding_model: Any) -> int:
        """
        Encodes chunk texts, populates the FAISS IndexFlatIP index, and maps vector positions to metadata.

        Args:
            chunks: List of chunk metadata dicts (from Section 2).
            embedding_model: EmbeddingModel instance.

        Returns:
            Total number of vectors indexed.
        """
        if not chunks:
            return 0

        texts = [chunk["text"] for chunk in chunks]
        vectors = embedding_model.encode(texts, normalize=True)

        if faiss is None:
            raise ImportError("faiss-cpu is required. Install using: pip install faiss-cpu")

        self._init_index()
        self.index.add(vectors)

        self.metadata_map = {idx: chunk for idx, chunk in enumerate(chunks)}
        return len(chunks)

    def save_index(self, index_path: Optional[str] = None, metadata_path: Optional[str] = None) -> None:
        """
        Persists FAISS index (.faiss) and metadata map (.json) to disk.
        Default location: data/vector_store/
        """
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        default_dir = os.path.join(base_dir, "data", "vector_store")
        os.makedirs(default_dir, exist_ok=True)

        if not index_path:
            index_path = os.path.join(default_dir, "lecture_index.faiss")
        if not metadata_path:
            metadata_path = os.path.join(default_dir, "chunk_metadata.json")

        os.makedirs(os.path.dirname(os.path.abspath(index_path)), exist_ok=True)
        os.makedirs(os.path.dirname(os.path.abspath(metadata_path)), exist_ok=True)

        faiss.write_index(self.index, index_path)

        # Convert keys to string for JSON serialization
        str_metadata_map = {str(k): v for k, v in self.metadata_map.items()}
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(str_metadata_map, f, indent=2, ensure_ascii=False)

    def load_index(self, index_path: Optional[str] = None, metadata_path: Optional[str] = None) -> None:
        """
        Loads FAISS index (.faiss) and metadata map (.json) from disk.
        """
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        default_dir = os.path.join(base_dir, "data", "vector_store")

        if not index_path:
            index_path = os.path.join(default_dir, "lecture_index.faiss")
        if not metadata_path:
            metadata_path = os.path.join(default_dir, "chunk_metadata.json")

        if not os.path.exists(index_path):
            raise FileNotFoundError(f"FAISS index file not found at {index_path}")
        if not os.path.exists(metadata_path):
            raise FileNotFoundError(f"Metadata JSON file not found at {metadata_path}")

        if faiss is None:
            raise ImportError("faiss-cpu is required. Install using: pip install faiss-cpu")

        self.index = faiss.read_index(index_path)

        with open(metadata_path, "r", encoding="utf-8") as f:
            raw_map = json.load(f)
        self.metadata_map = {int(k): v for k, v in raw_map.items()}

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 5,
        course_id: Optional[str] = None,
        lecture_id: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Performs similarity search with metadata filtering (course_id, lecture_id, source_type).

        Args:
            query_vector: 2D numpy array of shape (1, 384) or 1D array of shape (384,).
            top_k: Number of relevant evidence chunks to return.
            course_id: Optional course filter (e.g. 'MIT_6_100L').
            lecture_id: Optional lecture filter (e.g. 'lec01').
            source_type: Optional source type filter ('transcript' or 'pdf').

        Returns:
            List of top_k matched chunk dictionaries containing similarity scores.
        """
        if self.index is None or self.index.ntotal == 0:
            return []

        if query_vector.ndim == 1:
            query_vector = np.expand_dims(query_vector, axis=0)

        # Over-fetch candidate results to guarantee top_k hits after filtering
        fetch_k = min(self.index.ntotal, max(top_k * 5, 20))
        scores, indices = self.index.search(query_vector, fetch_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1 or idx not in self.metadata_map:
                continue

            chunk = dict(self.metadata_map[idx])

            # Apply metadata filters if provided
            if course_id and chunk.get("course_id") != course_id:
                continue
            if lecture_id and chunk.get("lecture_id") != lecture_id:
                continue
            if source_type and chunk.get("source_type") != source_type:
                continue

            chunk["score"] = float(score)
            results.append(chunk)

            if len(results) >= top_k:
                break

        return results
