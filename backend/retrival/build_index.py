import json
import numpy as np

from pathlib import Path

from embedding import generate_embeddings
from vector_store import create_faiss_index, save_faiss_index


# --------------------------------------------------
# Project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TRANSCRIPT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "transcripts"
    / "lecture_01_chunks.json"
)

PDF_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "pdf_text"
    / "lecture_01_chunks.json"
)


# --------------------------------------------------
# Load chunks
# --------------------------------------------------

def load_chunks(file_path):

    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, list):
        return data

    if isinstance(data, dict) and "chunks" in data:
        return data["chunks"]

    raise ValueError(
        f"Unexpected JSON structure: {file_path}"
    )


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():

    # --------------------------------------------------
    # Load transcript chunks
    # --------------------------------------------------

    print("\nLoading transcript chunks...")

    transcript_chunks = load_chunks(
        TRANSCRIPT_FILE
    )

    print(
        f"Transcript chunks: {len(transcript_chunks)}"
    )


    # --------------------------------------------------
    # Load PDF chunks
    # --------------------------------------------------

    print("\nLoading PDF chunks...")

    pdf_chunks = load_chunks(
        PDF_FILE
    )

    print(
        f"PDF chunks: {len(pdf_chunks)}"
    )


    # --------------------------------------------------
    # Combine transcript + PDF
    # --------------------------------------------------

    all_chunks = (
        transcript_chunks
        + pdf_chunks
    )

    print(
        f"\nTotal chunks: {len(all_chunks)}"
    )


    # --------------------------------------------------
    # Extract text
    # --------------------------------------------------

    texts = []
    valid_chunks = []

    for chunk in all_chunks:

        text = chunk.get("text", "").strip()

        if text:

            texts.append(text)
            valid_chunks.append(chunk)

    print(
        f"Chunks with text: {len(texts)}"
    )


    # --------------------------------------------------
    # Generate embeddings
    # --------------------------------------------------

    print("\nGenerating embeddings...")

    embeddings = generate_embeddings(
        texts
    )

    print(
        f"\nEmbedding matrix shape: {embeddings.shape}"
    )


    # --------------------------------------------------
    # Create output directory
    # --------------------------------------------------

    output_dir = (
        PROJECT_ROOT
        / "data"
        / "vector_store"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )


    # --------------------------------------------------
    # Save embeddings
    # --------------------------------------------------

    embeddings_file = (
        output_dir
        / "embeddings.npy"
    )

    np.save(
        embeddings_file,
        embeddings
    )

    print(
        f"Embeddings saved to: {embeddings_file}"
    )


    # --------------------------------------------------
    # Create chunk mapping
    # --------------------------------------------------

    mapping_file = (
        output_dir
        / "chunk_mapping.json"
    )

    mapping = []

    for index, chunk in enumerate(valid_chunks):

        mapping.append({
            "vector_id": index,
            "chunk_id": chunk["chunk_id"],
            "course_id": chunk["course_id"],
            "lecture_id": chunk["lecture_id"],
            "source_type": chunk["source_type"],
            "source_file": chunk["source_file"],
            "page": chunk.get("page"),
            "start_time": chunk.get("start_time"),
            "end_time": chunk.get("end_time"),
            "text": chunk["text"]
        })


    # IMPORTANT:
    # This is outside the for loop.

    with open(
        mapping_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            mapping,
            file,
            indent=2,
            ensure_ascii=False
        )

    print(
        f"Mapping saved to: {mapping_file}"
    )


    # --------------------------------------------------
    # Create FAISS index
    # --------------------------------------------------

    print("\nCreating FAISS index...")

    faiss_index = create_faiss_index(
        embeddings
    )

    print(
        f"Number of vectors in FAISS: {faiss_index.ntotal}"
    )

    print(
        f"Vector dimension: {faiss_index.d}"
    )


    # --------------------------------------------------
    # Save FAISS index
    # --------------------------------------------------

    faiss_file = (
        output_dir
        / "lecture_index.faiss"
    )

    save_faiss_index(
        faiss_index,
        faiss_file
    )

    print(
        f"FAISS index saved to: {faiss_file}"
    )


    # --------------------------------------------------
    # Done
    # --------------------------------------------------

    print("\n===================================")
    print("BUILD COMPLETE")
    print("===================================")

    print(
        f"Embeddings : {embeddings_file}"
    )

    print(
        f"Mapping    : {mapping_file}"
    )

    print(
        f"FAISS      : {faiss_file}"
    )


# --------------------------------------------------
# Run
# --------------------------------------------------

if __name__ == "__main__":
    main()