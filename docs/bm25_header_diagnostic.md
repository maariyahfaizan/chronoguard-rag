# Synthetic BM25 header diagnostic

This is a two-example synthetic diagnostic, not an attack success evaluation.
It asks whether a non-freshness header reproduces the previously observed rank
reversal. It reads no real Week 6 examples or heldout data, loads no model, and
does not invoke the older ranking runner's default CLI.

Only three conditions are scored: neutral, `Latest update:\n`, and
`General notice:\n`. Each contains correct then poison evidence. The original
neutral record comes from the committed construction builder; the diagnostic
copies it and changes only the leading poison text. Header labels live outside
that record: its original `condition` and `freshness_cue` metadata remain as
supplied by the neutral builder. Neither original passages nor source files are
overwritten. Claims, queries, document IDs/order, answers, timestamps, and other
metadata are fixed. Removing the exact header must recover neutral bytes.

## Tokenizers and controls

Each of the two examples is scored under all three headers and both tokenizers:
12 measurements, 24 passage score/rank entries, and 12 paired comparisons.

| Tokenizer label | Definition | Status |
| --- | --- | --- |
| `frozen_space_split` | Query and passages use `split(" ")` | Existing frozen BM25 function, unchanged |
| `diagnostic_whitespace_split` | Query and passages use `split()` | Separate diagnostic; not the frozen retriever |

For these inputs poison lengths are 9 neutral and 10 for either header under
space splitting; they are 9 neutral and 11 for either header under whitespace
splitting. Both standalone headers have two tokens under both tokenizers.
Equal counts are structural controls, not evidence of semantic equivalence.
`Latest update` asserts recency; `General notice` does not. The manifest records
this distinction and exact differing tokens/query overlaps for each example.
Space splitting fuses `update:\nThe` or `notice:\nThe`; whitespace splitting
retains `The` separately. Case, punctuation, and query text are not normalized.

## Scoring and independent reconstruction

Real execution requires exactly `rank-bm25==0.2.2`; missing or different versions
stop execution. No installation, download, fallback scorer, clamping, score
normalization, or positive-IDF substitution occurs. Both modes use BM25Okapi
k1=1.5, b=0.75, epsilon=0.25. The frozen function receives top_k=20 and returns
both documents. Diagnostic mode obtains actual scores from BM25Okapi and uses
stable descending sorting to report its own original output order.

The scalar reconstruction independently computes document frequencies, raw IDF
`log(N-df+0.5) - log(df+0.5)`, their mean, and effective IDFs. Negative raw IDFs
are replaced with `epsilon * average_raw_idf`, which may remain negative.
For each occurrence of each query token, its document contribution is:

```text
effective_idf * tf * (k1+1) / (tf + k1*(1-b+b*document_length/average_length))
```

An absent token contributes zero. Duplicate query tokens contribute repeatedly.
The reconstruction does not call `get_scores` or read library term frequencies
or IDFs to calculate contributions. It checks independently derived mean/effective
IDFs against the library, then checks the summed contributions against actual
`get_scores` scores and the frozen function's returned scores. All checks use
`math.isclose(rel_tol=1e-12, abs_tol=1e-12)` and reject nonfinite values.
A discrepancy is an error, never a reason to modify recorded scores.

Each measurement retains corpus/query tokens, lengths, average length, document
frequencies, vocabulary size, raw/effective IDFs, negative-IDF adjustment,
library IDFs, raw scores, token contributions, independent totals/residuals,
exact ties, original ranks, separate deterministic ranks, and poison-minus-correct
margin. Original output order is preserved. Deterministic order sorts by score
descending, then original candidate index. Exact ties favor correct evidence by
input order; this is not a relevance judgment. Near ties are not collapsed.

Comparisons report target minus reference for freshness versus neutral, general
notice versus neutral, and freshness versus general notice. Per-passage raw score
deltas, original-rank deltas, deterministic-rank deltas, and margin deltas remain
separate. Negative rank delta means improvement. Corpus statistics are fitted
separately per condition: score differences include the whole scoring procedure,
not isolated semantic effects. Token traces help inspect matching, IDF, and length
effects but do not fully identify their separate causal contributions.

## Commands and artifact protection

Local focused tests (real scoring tests explicitly skip without the pinned package):

```powershell
python -B -m pytest tests/test_bm25_header_diagnostic.py tests/test_freshness_smoke.py -q
```

In the existing Kaggle checkout, after transferring these three new files:

```bash
python -B -c "import rank_bm25; from importlib.metadata import version; assert version('rank-bm25') == '0.2.2'; print(version('rank-bm25'))"
python -B -m pytest tests/test_bm25_header_diagnostic.py tests/test_freshness_smoke.py -q
python -B -m src.eval.bm25_header_diagnostic \
  --prior-dir /kaggle/working/chronoguard_smoke_results/bm25_v1 \
  --out-dir /kaggle/working/chronoguard_smoke_results/bm25_header_controls_v1 \
  --repeat-check
sha256sum /kaggle/working/chronoguard_smoke_results/bm25_header_controls_v1/results.jsonl
```

Repeat checking is always enforced, including without the compatibility flag.
Execution inventories SHA-256 of every existing file under the prior directory,
including prior checksum records; hashes must match before/after scoring and
after output writing. The prior directory must exist, be nonempty, and contain
no symlinks. Hash preservation verifies unchanged bytes relative to this run's
initial snapshot; it does not certify agreement with an external historical hash.

The output directory must be new and cannot overlap prior results. Existing
outputs are never overwritten. The runner validates actual deserialized JSONL
identities, measurements, contribution totals, and comparison arithmetic.
It writes canonical UTF-8/LF `results.jsonl`, `validation.json` containing prior
before/after hashes, and `sha256.json` for the two new files. The checksum record
does not hash itself. An error after writing leaves the new artifacts for
inspection, without repairing or deleting anything. Prior files are never opened
for writing. Concurrent external edits fail preservation checks.

Canonical serialization sorts keys and rejects NaN/Infinity; no clock timestamps
are included. Repeated in-process runs must produce identical bytes. The manifest
pins Python/package versions, parameters, tolerances and relevant source hashes.
Floating-point results are not promised bit-identical across environments.

Local tests do not establish Kaggle results. If the non-freshness control also
produces poison-first ordering, freshness wording is unnecessary for that
observed reversal. This supports a scoring-confound explanation for these inputs,
not a general conclusion about semantic understanding or attack success. The
earlier subprocess hang remains unresolved and is not investigated here.
