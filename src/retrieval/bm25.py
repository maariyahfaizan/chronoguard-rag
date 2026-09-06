from rank_bm25 import BM25Okapi


def retrieve_best(query, candidates, top_k=1):
    """
    Rank candidates by BM25 score.

    Returns a list of (index, passage, score) tuples, where `index` is the
    passage's position in the original `candidates` list. Carrying the index
    alongside the text lets every downstream consumer identify a passage
    unambiguously, even when two candidates share identical text -- which
    list.index() cannot do (it always returns the first match).
    """
    tokenized_corpus = [c.split(" ") for c in candidates]
    bm25 = BM25Okapi(tokenized_corpus)
    tokenized_query = query.split(" ")
    scores = bm25.get_scores(tokenized_query)

    indexed = list(enumerate(candidates))  # [(0, passage0), (1, passage1), ...]
    ranked = sorted(zip(indexed, scores), key=lambda x: x[1], reverse=True)

    return [(idx, passage, float(score)) for (idx, passage), score in ranked[:top_k]]