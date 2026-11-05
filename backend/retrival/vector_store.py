import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.paths import get_lecture_paths, validate_identifier

# Try importing faiss; if blocked by Windows Application Control or missing, use pure NumPy fallback
try:
    import faiss
    _HAS_FAISS = True
except Exception:
    _HAS_FAISS = False


class NumpyIndexFlatIP:
    """
    Pure NumPy implementation of FAISS IndexFlatIP (cosine similarity / inner product search).
    Provides 100% API compatibility with faiss.IndexFlatIP for .add(), .search(), .ntotal, and .d.
    Used as an automatic fallback when C-extension DLLs are blocked on Windows.
    """

    def __init__(self, dimension: int):
        self.dimension = int(dimension)
        self.embeddings = np.empty((0, self.dimension), dtype=np.float32)

    @property
    def ntotal(self) -> int:
        return int(self.embeddings.shape[0])

    @property
    def d(self) -> int:
        return self.dimension

    def add(self, embeddings: np.ndarray) -> None:
        arr = np.asarray(embeddings, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        if arr.shape[1] != self.dimension:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.dimension}, got {arr.shape[1]}"
            )
        if self.embeddings.shape[0] == 0:
            self.embeddings = arr
        else:
            self.embeddings = np.vstack([self.embeddings, arr])

    def search(self, query_embedding: np.ndarray, top_k: int) -> Tuple[np.ndarray, np.ndarray]:
        q = np.asarray(query_embedding, dtype=np.float32)
        if q.ndim == 1:
            q = arr_q = q.reshape(1, -1)
        else:
            arr_q = q

        num_vectors = self.embeddings.shape[0]
        if num_vectors == 0:
            return (
                np.empty((arr_q.shape[0], 0), dtype=np.float32),
                np.empty((arr_q.shape[0], 0), dtype=np.int64),
            )

        k = min(top_k, num_vectors)
        # Inner product (cosine similarity since embeddings are normalized)
        sim_matrix = arr_q @ self.embeddings.T

        scores_list = []
        ids_list = []
        for row in sim_matrix:
            sorted_indices = np.argsort(-row)[:k]
            scores_list.append(row[sorted_indices])
            ids_list.append(sorted_indices)

        return np.array(scores_list, dtype=np.float32), np.array(ids_list, dtype=np.int64)


def create_faiss_index(embeddings: np.ndarray) -> Any:
    """
    Create a FAISS index using cosine similarity.
    Since the embeddings are normalized, inner product = cosine similarity.
    Falls back to NumPy implementation if FAISS DLLs are blocked on Windows.
    """
    arr = np.asarray(embeddings, dtype=np.float32)
    if arr.ndim != 2 or arr.shape[0] == 0:
        raise ValueError("Embeddings must be a non-empty 2D float32 array to create an index.")

    dimension = arr.shape[1]

    if _HAS_FAISS:
        try:
            index = faiss.IndexFlatIP(dimension)
            index.add(np.ascontiguousarray(arr, dtype=np.float32))
            return index
        except Exception:
            pass

    index = NumpyIndexFlatIP(dimension)
    index.add(arr)
    return index


def save_faiss_index(index: Any, file_path: Union[str, Path]) -> None:
    """Save index to disk."""
    target_path = Path(file_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if _HAS_FAISS and not isinstance(index, NumpyIndexFlatIP):
        try:
            faiss.write_index(index, str(target_path))
            return
        except Exception:
            pass

    if hasattr(index, "embeddings"):
        vecs = index.embeddings
    elif hasattr(index, "reconstruct"):
        num_vecs = index.ntotal
        vecs = np.array([index.reconstruct(i) for i in range(num_vecs)], dtype=np.float32)
    else:
        raise ValueError("Unsupported index object could not be serialized.")

    with open(target_path, "wb") as f:
        np.save(f, vecs)


def load_faiss_index(file_path: Union[str, Path]) -> Any:
    """
    Load an existing lecture FAISS index from disk.
    Never falls back to any global index path.
    """
    target_path = Path(file_path)
    if not target_path.exists():
        raise FileNotFoundError(f"FAISS index file not found at: {target_path}")

    if _HAS_FAISS:
        try:
            return faiss.read_index(str(target_path))
        except Exception:
            pass

    with open(target_path, "rb") as f:
        data = np.load(f)

    if data.ndim != 2 or data.shape[0] == 0:
        raise ValueError(f"Invalid or empty vector index data in: {target_path}")

    dim = data.shape[1]
    index = NumpyIndexFlatIP(dim)
    index.add(data)
    return index


def validate_and_load_knowledge_base(
    course_id: str,
    lecture_id: str,
    data_root: Optional[Union[str, Path]] = None,
) -> Tuple[Any, List[Dict[str, Any]]]:
    """
    Loads the exact selected lecture's isolated knowledge base from:
        {data_root}/lectures/{course_id}/{lecture_id}/knowledge_base/
    and strictly validates:
      1. Existence of knowledge_base/, index.faiss, chunk_mapping.json, and embeddings.npy
      2. Non-empty chunk mapping
      3. Exact length correspondence: index.ntotal == len(mapping) == embeddings.shape[0]
      4. 0-indexed vector_id alignment and strict course_id / lecture_id ownership for every chunk
    """
    valid_course_id = validate_identifier(course_id, "course_id")
    valid_lecture_id = validate_identifier(lecture_id, "lecture_id")
    lpaths = get_lecture_paths(valid_course_id, valid_lecture_id, data_root=data_root)

    if not lpaths.knowledge_base_dir.exists():
        raise FileNotFoundError(
            f"Knowledge base directory not found for {valid_course_id}/{valid_lecture_id}: "
            f"{lpaths.knowledge_base_dir}. Run run_lecture_pipeline.py for this lecture first."
        )

    if not lpaths.faiss_index.exists():
        raise FileNotFoundError(
            f"Missing FAISS index for {valid_course_id}/{valid_lecture_id}: {lpaths.faiss_index}"
        )

    if not lpaths.chunk_mapping.exists():
        raise FileNotFoundError(
            f"Missing chunk mapping for {valid_course_id}/{valid_lecture_id}: {lpaths.chunk_mapping}"
        )

    if not lpaths.embeddings.exists():
        raise FileNotFoundError(
            f"Missing embeddings file for {valid_course_id}/{valid_lecture_id}: {lpaths.embeddings}"
        )

    with open(lpaths.chunk_mapping, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    if not isinstance(mapping, list) or len(mapping) == 0:
        raise ValueError(
            f"Chunk mapping for {valid_course_id}/{valid_lecture_id} is empty or invalid: "
            f"{lpaths.chunk_mapping}"
        )

    index = load_faiss_index(lpaths.faiss_index)
    if index.ntotal != len(mapping):
        raise ValueError(
            f"Knowledge base mismatch for {valid_course_id}/{valid_lecture_id}: "
            f"FAISS index contains {index.ntotal} vectors, while chunk_mapping.json has {len(mapping)} entries."
        )

    embeddings_arr = np.load(str(lpaths.embeddings))
    if embeddings_arr.ndim != 2 or embeddings_arr.shape[0] != len(mapping):
        raise ValueError(
            f"Embeddings array mismatch for {valid_course_id}/{valid_lecture_id}: "
            f"embeddings.npy shape is {embeddings_arr.shape}, expected ({len(mapping)}, {index.d})."
        )

    for expected_vid, entry in enumerate(mapping):
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid mapping entry at index {expected_vid}: expected dict.")
        if entry.get("vector_id") != expected_vid:
            raise ValueError(
                f"Vector ID misalignment in {lpaths.chunk_mapping} at index {expected_vid}: "
                f"found vector_id={entry.get('vector_id')}."
            )
        if entry.get("course_id") != valid_course_id or entry.get("lecture_id") != valid_lecture_id:
            raise ValueError(
                f"Cross-lecture contamination detected in knowledge base {valid_course_id}/{valid_lecture_id}: "
                f"chunk '{entry.get('chunk_id')}' belongs to "
                f"{entry.get('course_id')}/{entry.get('lecture_id')}."
            )
        if not isinstance(entry.get("text"), str) or not entry["text"].strip():
            raise ValueError(
                f"Empty text in chunk mapping entry '{entry.get('chunk_id')}' at vector_id={expected_vid}."
            )

    return index, mapping
