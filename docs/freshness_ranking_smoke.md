# CPU synthetic retrieval-ranking diagnostics

Run from the repository root without installing packages or downloading models:

```powershell
python -B -m src.eval.freshness_ranking_smoke
python -B -m pytest tests/test_freshness_ranking_smoke.py tests/test_freshness_smoke.py -q
```

The runner prints deterministic JSONL to stdout and writes no result files.
It uses only the two fictional examples from the approved construction builder.
Two examples and one-to-two-document corpora provide construction and ranking
diagnostics only, not a meaningful attack success rate. No heldout or real Week 6
examples, archive scans, generation, GPU inference, or frozen-artifact edits occur.

Each example has clean (correct only), neutral poison (correct then poison), and
freshness poison (the same candidates, with exactly `Latest update:\n` prefixed
to poison `text`). The builder's validator runs before retrieval. Query, IDs,
timestamps, candidate order, incorrect claim body, and all other paired fields
are fixed. Metadata timestamps are not input to these retrievers.

The manifest records input-source/config hashes, package versions, model revision,
CPU settings, availability, parameters, and score definitions. Measurement rows
retain the complete construction input and its SHA-256, corpus statistics, and
separate BM25, dense, and hybrid views. Comparison rows report freshness minus
neutral and each poison condition minus clean. JSON keys are sorted, Unicode is
escaped, nonfinite scores are rejected, and LF endings are fixed. There are no
wall-clock timestamps. Byte reproducibility is expected in the same recorded
environment; floating-point results are not guaranteed identical across hardware
or library versions. Original retriever tie order is preserved even if unstable.

## Retrieval and tie handling

BM25 calls the existing `src/retrieval/bm25.py` with `top_k=20`. Dense calls the
existing dense retrieval function with `top_k=20`, attention-mask mean pooling,
and raw dot products. Hybrid uses the existing reciprocal-rank fusion function
with `rrf_k=60` and final limit 5. All documents therefore appear in each available
ranking. These parameters match the relevant Week 4 settings, but this tiny
corpus is not a reproduction of the baseline benchmark.

Every available view records `original_outputs` in the exact order returned,
with candidate index, passage text, score, and `original_rank`. It separately
records `deterministic_order` and `resolved_rank`: score descending, then original
candidate index ascending for exact ties. `score_tied` flags exact score ties;
near-equal floating-point values are not treated as ties. This adapter policy
does not change the frozen retrievers or imply their tie behavior is stable.
It favors the first (correct) candidate on ties, which must not be interpreted
as a relevance judgment.

RRF consumes the explicitly identified **deterministic component orders**, not
the original component orders. These orders are included in hybrid results.
Hybrid `original_outputs` denotes what the existing RRF function returned for
those supplied orders; it is not represented as the frozen end-to-end hybrid
driver's output. This checkpoint does not measure a second original-order hybrid
variant. If either component is unavailable, hybrid is unavailable too.

## Scores and comparisons

BM25 uses BM25Okapi defaults k1=1.5, b=0.75, epsilon=0.25 and the frozen
case-sensitive `split(' ')` tokenizer. In particular, the LF in the header is
not a space: `update:\nThe` becomes one token. Corpus statistics include document
count, per-document lengths, mean length, vocabulary size and document
frequencies; when BM25 is installed, they also include average and effective
IDFs and actual parameter values. Adding the header changes corpus statistics,
potentially including the average-IDF negative-IDF floor. Correct-passage scores
can change without changing its text. Tiny corpora can give negative scores.
Raw score differences measure this whole scoring procedure, not freshness
understanding. No alternative BM25 implementation is substituted.

Contriever scores are unnormalized mean-pooled dot products, comparable for
the same query/model/settings without corpus normalization. Changes may reflect
embedding direction or magnitude. Hybrid RRF scores are sums of
`1/(60 + one_based_component_rank)`, not similarity scores. Keep all three
retriever groups separate; do not pool or compare their score units.

Comparisons keep score deltas, original-rank deltas, resolved-rank deltas,
within-condition poison-minus-correct score margins, and margin deltas in distinct
fields. Negative rank delta means improved rank. Hybrid score fields contain
RRF scores, clearly identified by `retriever=hybrid`, never BM25/dense scores.
No per-condition min-max, softmax, or other normalization is applied.
Clean-to-poison comparisons are flagged as candidate-set changes: the clean
correct rank is trivially 1, and absent poison values are null with a reason.
These are not controlled estimates of the header effect; neutral-to-freshness
is the paired contrast.

## Local dependencies and model availability

No package installation or network access is performed. BM25 requires the
installed `rank-bm25` package (repository pin 0.2.2). Dense requires Torch,
Transformers, and huggingface-hub (repository pins 2.10.0, 5.0.0, 1.11.0).
The local snapshot must be exactly Contriever revision
`2bd46a25019aeea091fd42d1f0fd4801675cf699`. The runner inspects file sizes in
the Hugging Face cache and attempts local-only loading only when dependencies
and that directory exist. Cache folder naming is not cryptographic verification
of model-file contents. No other revision or remote fallback is used.

Loading bypasses the CUDA-selecting existing loader: model evaluation is float32
on CPU, with one CPU thread, deterministic Torch algorithms, and seed 42. Week 4
did not record model revisions; this later pin is not asserted to match its
historical model bytes. Load/import/inference failures yield explicit unavailable
statuses, not fabricated scores. Missing measurements have no deltas.

BM25 should take less than a second after imports; CPU model loading and this
tiny dense run may take seconds to minutes and several GB of RAM. Tests using
injected rankings validate arithmetic/control flow only, not real retrieval.
The real BM25 test is skipped explicitly when its dependency is absent.

A lexical scoring change, embedding change, or fusion rank change does not
establish that a retriever understands freshness. No answer adoption, attack
success, semantic certification, or historical provenance certification is
measured here. Real retrieval observations require available dependencies and
the exact model; this checkpoint never invents missing observations.
