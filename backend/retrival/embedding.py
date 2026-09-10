"""Reusable Sentence Transformer embeddings for KB documents and queries."""

from typing import Iterable

import numpy as np

DEFAULT_MODEL = "all-MiniLM-L6-v2"


class Embedder:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError("sentence-transformers is required. Install it with: pip install sentence-transformers") from exc
        self.model_name = model_name
        self._model = SentenceTransformer(model_name)

    def encode(self, texts: Iterable[str]) -> np.ndarray:
        values = list(texts)
        if not values:
            return np.empty((0, 0), dtype=np.float32)
        return np.asarray(self._model.encode(values, normalize_embeddings=True), dtype=np.float32)
