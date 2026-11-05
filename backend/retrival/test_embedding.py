import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.retrival.embedding import generate_embeddings


def main() -> None:
    texts = [
        "First normal form requires atomic attribute values.",
        "SQL inner join combines rows with matching join keys.",
        "Database transactions satisfy ACID properties.",
    ]

    embeddings = generate_embeddings(texts)

    print("Embedding shape:", embeddings.shape)
    print("First embedding (first 8 dims):")
    print(embeddings[0][:8])


if __name__ == "__main__":
    main()
