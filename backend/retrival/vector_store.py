"""Persistent vector search with FAISS when available and a NumPy fallback."""

import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np


class VectorStore:
    def __init__(self, vectors: np.ndarray, metadata: List[Dict[str, Any]]) -> None:
        if len(vectors) != len(metadata):
            raise ValueError("Each vector must have exactly one metadata record.")
        self.vectors = np.asarray(vectors, dtype=np.float32)
        self.metadata = metadata
        self._index = None
        try:
            import faiss
            self._index = faiss.IndexFlatIP(self.vectors.shape[1])
            self._index.add(self.vectors)
        except ImportError:
            pass

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "vectors.npy", self.vectors)
        (directory / "metadata.json").write_text(json.dumps(self.metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        if self._index is not None:
            import faiss
            faiss.write_index(self._index, str(directory / "index.faiss"))

    @classmethod
    def load(cls, directory: Path) -> "VectorStore":
        vectors = np.load(directory / "vectors.npy")
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        return cls(vectors, metadata)

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> List[Dict[str, Any]]:
        if not len(self.metadata):
            return []
        limit = min(top_k, len(self.metadata))
        query = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)
        if self._index is not None:
            scores, indices = self._index.search(query, limit)
            pairs = zip(scores[0], indices[0])
        else:
            scores = self.vectors @ query[0]
            indices = np.argsort(-scores)[:limit]
            pairs = ((scores[index], index) for index in indices)
        return [{"score": float(score), **self.metadata[int(index)]} for score, index in pairs]
