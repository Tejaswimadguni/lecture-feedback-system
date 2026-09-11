import numpy as np

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_st_model = None
_hf_tokenizer = None
_hf_model = None
_use_hf_fallback = False


def _init_model():
    """
    Initializes the embedding model.
    Tries SentenceTransformer first; if it fails (e.g. Windows DLL Application Control
    policy blocking scipy/sklearn), seamlessly falls back to pure PyTorch HuggingFace
    AutoTokenizer + BertModel with mean-pooling and L2 normalization.
    """
    global _st_model, _hf_tokenizer, _hf_model, _use_hf_fallback
    if _st_model is not None or (_hf_tokenizer is not None and _hf_model is not None):
        return

    try:
        from sentence_transformers import SentenceTransformer
        _st_model = SentenceTransformer("all-MiniLM-L6-v2")
        _use_hf_fallback = False
    except Exception as e:
        # Fallback to direct HuggingFace PyTorch BertModel (no scipy / sklearn dependencies)
        import torch
        from transformers import AutoTokenizer, BertModel

        _hf_tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _hf_model = BertModel.from_pretrained(MODEL_NAME)
        _hf_model.eval()
        _use_hf_fallback = True


def generate_embeddings(texts):
    """
    Generate normalized embeddings for multiple texts.
    Returns NumPy float32 array of shape (N, 384).
    """
    if not texts:
        return np.empty((0, 384), dtype=np.float32)

    _init_model()

    if not _use_hf_fallback and _st_model is not None:
        embeddings = _st_model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False
        )
        return embeddings.astype(np.float32)

    # HuggingFace PyTorch Mean-Pooling + L2-Normalize
    import torch
    import torch.nn.functional as F

    encoded = _hf_tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt"
    )

    with torch.no_grad():
        output = _hf_model(**encoded)
        token_embeddings = output[0]  # First element contains token embeddings
        attention_mask = encoded["attention_mask"].unsqueeze(-1).expand(token_embeddings.size()).float()
        sum_embeddings = torch.sum(token_embeddings * attention_mask, 1)
        sum_mask = torch.clamp(attention_mask.sum(1), min=1e-9)
        mean_pooled = sum_embeddings / sum_mask
        normalized = F.normalize(mean_pooled, p=2, dim=1)

    return normalized.cpu().numpy().astype(np.float32)


def generate_embedding(text):
    """
    Generate an embedding for a single text.
    Returns NumPy float32 array of shape (1, 384).
    """
    return generate_embeddings([text])