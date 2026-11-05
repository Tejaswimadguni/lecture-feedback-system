"""Retrieval and lecture-isolated FAISS vector store package."""

from .embedding import EmbeddingModel, generate_embedding, generate_embeddings
from .vector_store import (
    NumpyIndexFlatIP,
    create_faiss_index,
    load_faiss_index,
    save_faiss_index,
    validate_and_load_knowledge_base,
)
from .build_index import build_lecture_index
from .search import search

__all__ = [
    "EmbeddingModel",
    "generate_embedding",
    "generate_embeddings",
    "NumpyIndexFlatIP",
    "create_faiss_index",
    "load_faiss_index",
    "save_faiss_index",
    "validate_and_load_knowledge_base",
    "build_lecture_index",
    "search",
]
