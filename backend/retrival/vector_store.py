import numpy as np
from pathlib import Path

# Try importing faiss; if blocked by Windows Application Control or missing, use pure NumPy fallback
try:
    import faiss
    _HAS_FAISS = True
except Exception:
    _HAS_FAISS = False


class NumpyIndexFlatIP:
    """
    Pure NumPy implementation of FAISS IndexFlatIP (cosine similarity / inner product search).
    Provides 100% API compatibility with faiss.IndexFlatIP for .add() and .search().
    Used as an automatic fallback when C-extension DLLs are blocked on Windows.
    """
    def __init__(self, dimension: int):
        self.dimension = dimension
        self.embeddings = np.empty((0, dimension), dtype=np.float32)

    def add(self, embeddings: np.ndarray):
        arr = np.asarray(embeddings, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        if self.embeddings.shape[0] == 0:
            self.embeddings = arr
        else:
            self.embeddings = np.vstack([self.embeddings, arr])

    def search(self, query_embedding: np.ndarray, top_k: int):
        q = np.asarray(query_embedding, dtype=np.float32)
        if q.ndim == 1:
            q = q.reshape(1, -1)

        num_vectors = self.embeddings.shape[0]
        if num_vectors == 0:
            return np.empty((q.shape[0], 0), dtype=np.float32), np.empty((q.shape[0], 0), dtype=np.int64)

        k = min(top_k, num_vectors)
        # Inner product (cosine similarity since embeddings are normalized)
        sim_matrix = q @ self.embeddings.T

        scores_list = []
        ids_list = []
        for row in sim_matrix:
            sorted_indices = np.argsort(-row)[:k]
            scores_list.append(row[sorted_indices])
            ids_list.append(sorted_indices)

        return np.array(scores_list, dtype=np.float32), np.array(ids_list, dtype=np.int64)


def create_faiss_index(embeddings):
    """
    Create a FAISS index using cosine similarity.
    Since the embeddings are normalized, inner product = cosine similarity.
    Falls back to NumPy implementation if FAISS DLLs are blocked on Windows.
    """
    dimension = embeddings.shape[1]

    if _HAS_FAISS:
        try:
            index = faiss.IndexFlatIP(dimension)
            index.add(embeddings)
            return index
        except Exception:
            pass

    index = NumpyIndexFlatIP(dimension)
    index.add(embeddings)
    return index


def save_faiss_index(index, file_path):
    """
    Save index to disk.
    """
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if _HAS_FAISS:
        try:
            faiss.write_index(index, str(file_path))
            return
        except Exception:
            pass

    # Save NumPy embeddings array to file without modifying filename extension
    if hasattr(index, "embeddings"):
        vecs = index.embeddings
    elif hasattr(index, "reconstruct"):
        num_vecs = index.ntotal
        vecs = np.array([index.reconstruct(i) for i in range(num_vecs)], dtype=np.float32)
    else:
        vecs = np.empty((0, 384), dtype=np.float32)

    with open(file_path, "wb") as f:
        np.save(f, vecs)


def load_faiss_index(file_path):
    """
    Load an existing index from disk.
    """
    file_path = Path(file_path)

    if _HAS_FAISS:
        try:
            return faiss.read_index(str(file_path))
        except Exception:
            pass

    # Fallback to loading via NumPy (check both exact path and with .npy)
    actual_path = file_path
    if not actual_path.exists() and Path(str(file_path) + ".npy").exists():
        actual_path = Path(str(file_path) + ".npy")

    with open(actual_path, "rb") as f:
        data = np.load(f)

    dim = data.shape[1]
    index = NumpyIndexFlatIP(dim)
    index.add(data)
    return index