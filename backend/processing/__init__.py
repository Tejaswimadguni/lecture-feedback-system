"""
Processing package for lecture feedback system.
Contains transcript cleaner/chunker, PDF cleaner/chunker, and unified metadata definitions.
"""

from .transcript_cleaner import clean_transcript
from .transcript_chunker import chunk_transcript
from .pdf_cleaner import clean_pdf_pages
from .pdf_chunker import chunk_pdf
from .metadata import create_chunk_metadata, validate_chunk

__all__ = [
    "clean_transcript",
    "chunk_transcript",
    "clean_pdf_pages",
    "chunk_pdf",
    "create_chunk_metadata",
    "validate_chunk",
]
