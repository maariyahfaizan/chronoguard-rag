import torch
from transformers import AutoTokenizer, AutoModel


MODEL_NAME = "facebook/contriever"


def load_dense_model(model_name: str = MODEL_NAME):
    """Load the Contriever dense retriever."""

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model.eval()

    return model, tokenizer, device


def mean_pooling(token_embeddings, attention_mask):
    """Mean-pool token embeddings using the attention mask."""

    token_embeddings = token_embeddings.masked_fill(
        ~attention_mask[..., None].bool(),
        0.0
    )

    sentence_embeddings = token_embeddings.sum(dim=1) / (
        attention_mask.sum(dim=1)[..., None]
    )

    return sentence_embeddings


def encode_texts(texts, model, tokenizer, device, batch_size=16):
    """Convert a list of texts into dense embeddings."""

    all_embeddings = []

    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]

            inputs = tokenizer(
                batch,
                padding=True,
                truncation=True,
                return_tensors="pt"
            ).to(device)

            outputs = model(**inputs)

            embeddings = mean_pooling(
                outputs.last_hidden_state,
                inputs["attention_mask"]
            )

            all_embeddings.append(embeddings.cpu())

    return torch.cat(all_embeddings, dim=0)


def retrieve_best(
    query,
    candidates,
    model,
    tokenizer,
    device,
    top_k=5
):
    """Retrieve the top-k candidates using Contriever dot-product similarity."""

    query_embedding = encode_texts(
        [query],
        model,
        tokenizer,
        device,
        batch_size=1
    )[0]

    candidate_embeddings = encode_texts(
        candidates,
        model,
        tokenizer,
        device
    )

    scores = torch.matmul(
        candidate_embeddings,
        query_embedding
    )

    top_k = min(top_k, len(candidates))

    top_scores, top_indices = torch.topk(
        scores,
        k=top_k
    )

    ranked = [
        (candidates[int(index)], float(score))
        for index, score in zip(top_indices, top_scores)
    ]

    return ranked