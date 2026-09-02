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

    RRF score:
        score(d) = 1 / (rrf_k + rank_bm25(d))
                  + 1 / (rrf_k + rank_dense(d))

    Ranks are 1-based.
    """

    rrf_scores = {}

    # BM25 ranking
    for rank, (passage, score) in enumerate(bm25_results, start=1):
        if passage not in rrf_scores:
            rrf_scores[passage] = 0.0

        rrf_scores[passage] += 1.0 / (rrf_k + rank)

    # Dense ranking
    for rank, (passage, score) in enumerate(dense_results, start=1):
        if passage not in rrf_scores:
            rrf_scores[passage] = 0.0

        rrf_scores[passage] += 1.0 / (rrf_k + rank)

    # Sort by fused RRF score
    ranked = sorted(
        rrf_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )

    return ranked[:top_k]


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
    """
    Retrieve candidates using BM25 + Contriever and fuse
    the rankings using RRF.
    """

    # -------------------------
    # BM25 retrieval
    # -------------------------

    bm25_results = bm25_retrieve(
        query,
        candidates,
        top_k=candidate_top_k
    )

    # -------------------------
    # Dense retrieval
    # -------------------------

    dense_results = dense_retrieve(
        query,
        candidates,
        retriever_model,
        retriever_tokenizer,
        retriever_device,
        top_k=candidate_top_k
    )

    # -------------------------
    # RRF fusion
    # -------------------------

    fused_results = reciprocal_rank_fusion(
        bm25_results,
        dense_results,
        top_k=final_top_k,
        rrf_k=rrf_k
    )

    return bm25_results, dense_results, fused_results