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

    candidates must be a list of:
        (passage, score)

    Returns:
        (passage, reranker_score)
    """

    if not candidates:
        return []

    # Create query-document pairs.
    pairs = [
        [query, passage]
        for passage, score in candidates
    ]

    # Score every query-document pair.
    scores = model.predict(
        pairs,
        batch_size=batch_size,
        show_progress_bar=False
    )

    # Attach cross-encoder scores.
    ranked = [
        (passage, float(score))
        for (passage, _), score in zip(candidates, scores)
    ]

    # Highest score first.
    ranked.sort(
        key=lambda x: x[1],
        reverse=True
    )

    return ranked[:top_k]