import torch

from src.retrieval.bm25 import retrieve_best as bm25_retrieve
from src.retrieval.dense import retrieve_best as dense_retrieve


RRF_K = 60


def reciprocal_rank_fusion(
    bm25_results,
    dense_results,
    top_k=5,
    rrf_k=RRF_K
):
    """
    Fuse two ranked retrieval lists using Reciprocal Rank Fusion (RRF).

    bm25_results / dense_results: lists of (index, passage, score), where
    `index` is the passage's position in the original candidate list.

    Fusion keys on `index`, not passage text. Keying on text was the original
    bug: two distinct candidates that happen to share identical text would be
    silently merged into a single RRF entry, and it's also what forced every
    downstream script to fall back on candidates.index(text) for logging --
    which only recovers the FIRST matching index when text is duplicated.
    Keying on the index retrieval already computed removes the need for that
    lookup entirely.

    score(d) = 1 / (rrf_k + rank_bm25(d)) + 1 / (rrf_k + rank_dense(d))
    Ranks are 1-based.
    """

    rrf_scores = {}       # idx -> fused score
    passage_by_idx = {}   # idx -> passage text (so we can still return text)

    for rank, (idx, passage, score) in enumerate(bm25_results, start=1):
        rrf_scores[idx] = rrf_scores.get(idx, 0.0) + 1.0 / (rrf_k + rank)
        passage_by_idx[idx] = passage

    for rank, (idx, passage, score) in enumerate(dense_results, start=1):
        rrf_scores[idx] = rrf_scores.get(idx, 0.0) + 1.0 / (rrf_k + rank)
        passage_by_idx[idx] = passage

    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    return [
        (idx, passage_by_idx[idx], fused_score)
        for idx, fused_score in ranked[:top_k]
    ]


def retrieve_hybrid(
    query,
    candidates,
    retriever_model,
    retriever_tokenizer,
    retriever_device,
    candidate_top_k=20,
    final_top_k=5,
    rrf_k=RRF_K
):
    """Retrieve candidates using BM25 + Contriever and fuse via RRF."""

    bm25_results = bm25_retrieve(query, candidates, top_k=candidate_top_k)

    dense_results = dense_retrieve(
        query, candidates, retriever_model, retriever_tokenizer,
        retriever_device, top_k=candidate_top_k
    )

    fused_results = reciprocal_rank_fusion(
        bm25_results, dense_results, top_k=final_top_k, rrf_k=rrf_k
    )

    return bm25_results, dense_results, fused_results