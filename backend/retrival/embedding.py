# pyrefly: ignore [missing-import]
from sentence_transformers import SentenceTransformer
import numpy as np


MODEL_NAME = "all-MiniLM-L6-v2"

model = SentenceTransformer(MODEL_NAME)


def generate_embeddings(texts):
    """
    Generate normalized embeddings for multiple texts.
    """

    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True
    )

    return embeddings.astype(np.float32)


def generate_embedding(text):
    """
    Generate an embedding for a single text.
    """

    embedding = model.encode(
        [text],
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    return embedding.astype(np.float32)