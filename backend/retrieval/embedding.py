import numpy as np
from typing import Union, List


class EmbeddingModel:
    """
    Embedding model wrapper around SentenceTransformers.
    Uses 'all-MiniLM-L6-v2' (384-dimensional) by default for fast, lightweight local semantic embeddings.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.dimension = 384
        self._model = None

    @property
    def model(self):
        """Lazy loader for SentenceTransformer model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except ImportError as e:
                raise ImportError(
                    "sentence-transformers is required. Install using: pip install sentence-transformers"
                ) from e
        return self._model

    def encode(self, texts: Union[str, List[str]], normalize: bool = True) -> np.ndarray:
        """
        Encodes a single text string or list of text strings into 384-dimensional float32 vector embeddings.

        Args:
            texts: Single string or list of strings.
            normalize: Whether to L2-normalize vectors for cosine similarity search (default True).

        Returns:
            2D numpy array of shape (N, 384) with dtype float32.
        """
        is_single = isinstance(texts, str)
        text_list = [texts] if is_single else texts

        if not text_list:
            return np.empty((0, self.dimension), dtype=np.float32)

        # Generate embeddings
        embeddings = self.model.encode(text_list, show_progress_bar=False, convert_to_numpy=True)
        embeddings = np.asarray(embeddings, dtype=np.float32)

        if normalize:
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            embeddings = embeddings / norms

        return embeddings

    def similarity(self, text1: str, text2: str) -> float:
        """
        Calculates cosine similarity score between two text strings.

        Returns:
            Float score between -1.0 and 1.0.
        """
        vecs = self.encode([text1, text2], normalize=True)
        return float(np.dot(vecs[0], vecs[1]))


if __name__ == "__main__":
    embedder = EmbeddingModel()
    sample_texts = [
        "Python variables store values",
        "A variable is a name referring to a value",
        "The weather is sunny today"
    ]
    vecs = embedder.encode(sample_texts)
    print(f"Encoded shape: {vecs.shape}")
    sim_var = embedder.similarity(sample_texts[0], sample_texts[1])
    sim_weather = embedder.similarity(sample_texts[0], sample_texts[2])
    print(f"Similarity (var1, var2): {sim_var:.4f}")
    print(f"Similarity (var1, weather): {sim_weather:.4f}")
