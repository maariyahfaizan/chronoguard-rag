import torch
from sentence_transformers import CrossEncoder


MODEL_NAME = "BAAI/bge-reranker-base"


def load_reranker(model_name: str = MODEL_NAME):
    """
    Load the BGE cross-encoder reranker.
    """

    device = "cuda" if torch.cuda.is_available() else "cpu"

    print(f"Loading reranker: {model_name}")
    print(f"Reranker device: {device}")

    model = CrossEncoder(
        model_name,
        device=device
    )

    return model, device


def rerank(
    query,
    candidates,
    model,
    top_k=5,
    batch_size=8
):
    """
    Rerank candidates using the BGE cross-encoder.

    `candidates` must be a list of (index, passage, score), matching the
    output of retrieve_best / reciprocal_rank_fusion.

    Returns (index, passage, reranker_score) -- the index is preserved so
    the caller never needs to re-look-up the passage by text.
    """

    if not candidates:
        return []

    pairs = [[query, passage] for idx, passage, score in candidates]

    scores = model.predict(pairs, batch_size=batch_size, show_progress_bar=False)

    ranked = [
        (idx, passage, float(score))
        for (idx, passage, _), score in zip(candidates, scores)
    ]

    ranked.sort(key=lambda x: x[2], reverse=True)

    return ranked[:top_k]