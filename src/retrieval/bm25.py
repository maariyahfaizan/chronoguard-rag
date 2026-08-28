from rank_bm25 import BM25Okapi 

def retrieve_best(query, candidates, top_k=1):
    tokenized_corpus = [c.split(" ") for c in candidates]
    bm25 = BM25Okapi(tokenized_corpus)
    tokenized_query = query.split(" ")
    scores = bm25.get_scores(tokenized_query) # scores the candidates based on the query
    ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True) # group the candidates with their scores and sort them in descending order
    return ranked[:top_k]