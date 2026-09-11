from embedding import generate_embeddings


texts = [
    "Variables can store values.",
    "Python is a programming language.",
    "Computation can be used to solve problems."
]


embeddings = generate_embeddings(texts)

print("Embedding shape:", embeddings.shape)
print("First embedding:")
print(embeddings[0])