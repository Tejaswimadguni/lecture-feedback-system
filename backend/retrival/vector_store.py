# pyrefly: ignore [missing-import]
import faiss
import numpy as np
from pathlib import Path


def create_faiss_index(embeddings):
    """
    Create a FAISS index using cosine similarity.

    Since the embeddings are normalized,
    inner product = cosine similarity.
    """

    dimension = embeddings.shape[1]

    index = faiss.IndexFlatIP(dimension)

    index.add(embeddings)

    return index


def save_faiss_index(index, file_path):
    """
    Save FAISS index to disk.
    """

    file_path = Path(file_path)

    file_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    faiss.write_index(
        index,
        str(file_path)
    )


def load_faiss_index(file_path):
    """
    Load an existing FAISS index.
    """

    return faiss.read_index(
        str(file_path)
    )