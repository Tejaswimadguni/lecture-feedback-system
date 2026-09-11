import os
import json
import logging
from typing import List, Dict, Any, Optional

try:
    from .embedding import EmbeddingModel
    from .vector_store import VectorStore
except ImportError:
    from embedding import EmbeddingModel
    from vector_store import VectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class SemanticSearch:
    """
    Semantic Search engine combining SentenceTransformer embeddings with FAISS vector indexing
    and metadata filtering for claim verification and evidence retrieval.
    """

    def __init__(
        self,
        embedding_model: Optional[EmbeddingModel] = None,
        vector_store: Optional[VectorStore] = None
    ):
        self.embedding_model = embedding_model or EmbeddingModel()
        self.vector_store = vector_store or VectorStore()

    def index_processed_dataset(
        self,
        transcripts_chunks_path: Optional[str] = None,
        pdf_chunks_path: Optional[str] = None,
        save: bool = True
    ) -> int:
        """
        Loads processed transcript and PDF chunks, embeds them, populates FAISS vector store,
        and saves index to disk.

        Returns:
            Total number of chunks indexed.
        """
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

        if not transcripts_chunks_path:
            transcripts_chunks_path = os.path.join(base_dir, "data", "processed", "transcripts", "lecture_01_chunks.json")
        if not pdf_chunks_path:
            pdf_chunks_path = os.path.join(base_dir, "data", "processed", "pdf_text", "lecture_01_chunks.json")

        all_chunks = []

        if os.path.exists(transcripts_chunks_path):
            with open(transcripts_chunks_path, "r", encoding="utf-8") as f:
                t_chunks = json.load(f)
                all_chunks.extend(t_chunks)
                logger.info(f"Loaded {len(t_chunks)} transcript chunks from {transcripts_chunks_path}")

        if os.path.exists(pdf_chunks_path):
            with open(pdf_chunks_path, "r", encoding="utf-8") as f:
                p_chunks = json.load(f)
                all_chunks.extend(p_chunks)
                logger.info(f"Loaded {len(p_chunks)} PDF chunks from {pdf_chunks_path}")

        if not all_chunks:
            logger.warning("No chunks found to index!")
            return 0

        logger.info(f"Generating embeddings for {len(all_chunks)} chunks...")
        num_indexed = self.vector_store.build_index(all_chunks, self.embedding_model)

        if save:
            self.vector_store.save_index()
            logger.info("Saved FAISS index and chunk metadata to data/vector_store/")

        return num_indexed

    def load_existing_index(self, index_path: Optional[str] = None, metadata_path: Optional[str] = None) -> None:
        """Loads pre-built FAISS index and metadata store."""
        self.vector_store.load_index(index_path, metadata_path)

    def search(
        self,
        query: str,
        top_k: int = 5,
        course_id: Optional[str] = None,
        lecture_id: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Executes semantic search for a user claim/query string.

        Args:
            query: Natural language claim or question (e.g. 'What is a Python variable?').
            top_k: Number of relevant evidence chunks to return (default 5).
            course_id: Optional course filter (e.g. 'MIT_6_100L').
            lecture_id: Optional lecture filter (e.g. 'lec01').
            source_type: Optional source filter ('transcript' or 'pdf').

        Returns:
            List of top_k matched evidence chunk dictionaries containing similarity scores.
        """
        query_vector = self.embedding_model.encode(query, normalize=True)
        return self.vector_store.search(
            query_vector=query_vector,
            top_k=top_k,
            course_id=course_id,
            lecture_id=lecture_id,
            source_type=source_type
        )


def main():
    search_engine = SemanticSearch()
    search_engine.index_processed_dataset()

    sample_queries = [
        "What is a Python variable?",
        "How did the lecturer explain computation?",
        "What practice problems or psets were discussed?",
    ]

    print("\n=========================================")
    print(" Executing Semantic Search Queries ")
    print("=========================================")

    for q in sample_queries:
        print(f"\nQUERY: '{q}'")
        results = search_engine.search(q, top_k=3)
        for rank, res in enumerate(results, start=1):
            source_info = f"Transcript ({res.get('start_time'):.1f}s-{res.get('end_time'):.1f}s)" if res.get("source_type") == "transcript" else f"PDF (Page {res.get('page')})"
            clean_print_text = res['text'][:120].replace('\uf0a7', '-').encode('ascii', errors='backslashreplace').decode('ascii')
            print(f"  [{rank}] Score: {res['score']:.4f} | Chunk ID: {res['chunk_id']} | Source: {source_info}")
            print(f"      Text: {clean_print_text}...")


if __name__ == "__main__":
    main()
