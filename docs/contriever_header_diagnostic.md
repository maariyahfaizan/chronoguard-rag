# Controlled Contriever header diagnostic

This is a two-example synthetic diagnostic, not a benchmark attack-success
evaluation. It uses only the committed fictional Luma Observatory and Cedar Cup
examples. It does not generate answers, access heldout data, run hybrid retrieval,
or infer semantic understanding from embedding differences.

## Fixed design

Each example has three conditions: neutral poison, `Latest update:\n`, and
`General notice:\n`. The committed BM25 condition renderer is reused without
calling BM25 scoring. Only the leading poison text changes. Removing the exact
header recovers the neutral record. Query, false claim, correct passage,
candidate IDs, correct-then-poison ordering, timestamps, answers, and all metadata
remain identical. Input metadata retains the builder's `neutral_poison` label and
empty cue; diagnostic condition labels are outside that record.

There are six measurements, twelve passage scores, and six paired comparisons.
**Freshness minus general_notice is the primary contrast** for each example.
Freshness minus neutral and general_notice minus neutral are secondary.
All differences are target minus reference. Negative rank changes mean improvement.
Margins are poison score minus correct score. No significance tests or population
claims are appropriate for these two examples.

## Model identity and prerequisites

The runner requires `facebook/contriever` revision
`2bd46a25019aeea091fd42d1f0fd4801675cf699` and requires the committed
`configs/model_revisions.yaml` pin to agree. A snapshot directory name alone does
not prove which model its bytes contain. Supply an **independently trusted**
SHA-256 inventory tied to that model and revision:

```json
{
  "model": "facebook/contriever",
  "revision": "2bd46a25019aeea091fd42d1f0fd4801675cf699",
  "files": {
    "config.json": "<64 lowercase hex characters>",
    "pytorch_model.bin": "<64 lowercase hex characters>",
    "tokenizer.json": "<64 lowercase hex characters>",
    "tokenizer_config.json": "<64 lowercase hex characters>",
    "special_tokens_map.json": "<64 lowercase hex characters>",
    "vocab.txt": "<64 lowercase hex characters>"
  }
}
```

Include every snapshot file. Do not create this trust anchor by hashing the
unverified snapshot itself: that establishes only self-consistency, not identity.
Obtain it from independently authenticated revision artifacts or a previously
verified archive. No trusted inventory is bundled and no network verification or
download is performed. This is a prerequisite for real execution.

The snapshot must be a real directory named by the full revision. HF file
symlinks are permitted and their resolved contents are hashed; directory symlinks
and broken links fail. Missing, extra, or altered files fail. Require all listed
tokenizer files and exactly one unsharded `pytorch_model.bin` or
`model.safetensors`; sharded/ambiguous snapshots are deliberately unsupported.
Configuration must identify a 12-layer, 768-dimensional BERT model. Actual loading
must have no missing, unexpected, mismatched, or error keys and must produce a
compatible fast tokenizer and vocabulary size. Compatibility failure stops
before forward inference. There is no alternative model or scoring fallback.

Real execution requires the repository pins `torch==2.10.0`,
`transformers==5.0.0`, and `huggingface-hub==1.11.0` (Torch build suffixes are
recorded and allowed). Transitive dependencies, including tokenizer packages,
must already be installed; exact installed versions are recorded. This runner
does not install anything. CPU execution requires no GPU; budget several GB of
host memory as an estimate. Snapshot compatibility and real inference remain
unverified until explicitly executed in a prepared environment.

## Encoding, scoring, and confounds

The existing `src/retrieval/dense.py` is unchanged. Its `retrieve_best` is called
with `top_k=20`, returning both candidates. Load locally with remote code disabled;
set offline mode, CPU float32, `.eval()`, seed 42, one intra-operation thread, one
inter-operation thread, and deterministic algorithms. Use a fresh process because
Torch inter-operation settings cannot always be changed after work has begun.

Queries use batch size 1; both candidates share one batch through the existing
default size 16. The tokenizer uses padding and truncation with its loaded
defaults. Pooling averages the final hidden state over all attended tokens,
including attended special tokens. No L2 or corpus normalization occurs. Embeddings
move to CPU, where the retriever computes raw dot products and `torch.topk`.

Original `torch.topk` order is retained; it offers no index tie policy in this
implementation. A separately named resolved rank sorts exact scores descending,
then candidate index ascending. Exact ties therefore favor the correct passage
in the resolved view because it is first in the fixed input. Near ties remain
distinct. This is an ordering convention, not a relevance judgment.

Audit actual fast-tokenizer IDs, token strings, attention/special/type masks,
offsets, effective and untruncated lengths, padded inputs, body token positions,
body-relative offsets, exact UTF-8 hashes, and byte lengths. Reproduce the
retriever's query and candidate batching for the audit. Reject any truncation.
Structural matching requires equal effective lengths and identical body-token
IDs, positions, and relative offsets across the two headers. Header token IDs
are intentionally different. Record failed matching as explicit structural
confounds; do not rewrite headers or suppress those results.

BM25 whitespace counts do not establish this matching. The loaded tokenizer may
normalize case, punctuation, or newlines. Its backend configuration, special
tokens, options, and maximum length are recorded. A matching structure still
does not isolate semantics: lexical identity, contextual representations,
position effects, pooling, and embedding magnitude can affect scores. Neutral
versus either header additionally changes length. Do not interpret any contrast
as a causal decomposition of these factors.

Save full query/candidate vectors, float32 dtype, dimensions, norms, and canonical
vector hashes. A separate invocation of the unchanged encoder obtains audit
vectors; independently sum their products with `math.fsum` and compare against
actual retrieval scores using `atol=rtol=1e-5`. Save residuals; never replace raw
retrieval scores. This checks arithmetic, not an independent neural-model
implementation. Record whether unchanged query/correct vectors drift across
conditions; do not force equality. Padding changes may affect numerical execution.

## Provenance and outputs

`results.jsonl` contains one manifest, six measurements, and six comparisons.
The manifest records revision/file hashes, trusted-manifest hash, source and
configuration hashes, Git commit/status, Python/platform/CPU metadata, package
versions, Torch build/thread/determinism settings, tokenizer/model configuration,
scoring rules, tolerances, and interpretation limits.

`embeddings.jsonl` contains six records pairing query and candidate vectors with
example/condition identities. `validation.json` records coverage, repeat checks,
invariant-vector audits, prior before/after inventories, and known archive checks.
`sha256.json` hashes the other three files; it does not hash itself.
JSON uses canonical sorted keys, UTF-8/LF, and finite numbers, with no clock fields.
Deserialize and validate identities, vector hashes, arithmetic, and contrasts.

Repeat all measurements in-process and require identical bytes. That establishes
same-environment repeatability only. It is neither evidence of semantic freshness
preference nor a cross-environment bitwise guarantee. Model/configuration paths
and Git status are provenance, so manifests can differ between environments.

Protect every supplied prior directory with recursive SHA-256 inventories,
including existing checksum files. Check before/after scoring and after writing;
never open protected files for writing. Prior directories must be nonempty and
contain no symlinks. Verify these historical hashes when supplied directly as
named directories or nested under a supplied parent:

| Relative archive file | Expected SHA-256 |
| --- | --- |
| `bm25_v1/results.jsonl` | `f55b9df259b55bee5f3c29a24db9b0fe48e94365742d70a63a496b6fe952cb51` |
| `bm25_header_controls_v1/results.jsonl` | `343cf43e883780003247a3adc46d55eef1fd1ade07c4d623b2a1136d8a928527` |

Absent archives are marked `not_supplied`, never historically verified. Other
files have preservation checks relative to the current run's initial inventory.
Output must be new and nonoverlapping with protected results, model inputs, and
source/configuration directories. Files use exclusive creation. Existing output
directories are refused even when empty. Errors after writing leave artifacts
for inspection; the runner never repairs or deletes them. Concurrent external
changes are detected by inventories rather than prevented by filesystem locks.

## Commands

Local bookkeeping tests do not import Torch/Transformers or execute real inference:

```powershell
python -B -m pytest tests/test_contriever_header_diagnostic.py tests/test_bm25_header_diagnostic.py tests/test_freshness_smoke.py -q
python -B -m src.eval.contriever_header_diagnostic --help
git diff --check
```

Metadata/file-only preflight (no model loading):

```powershell
python -B -m src.eval.contriever_header_diagnostic --preflight-only --model-snapshot $snapshotPath --snapshot-manifest $trustedManifestPath --prior-dir $bm25Path --prior-dir $bm25HeaderPath
```

Only when separately authorized in a prepared environment, invoke real inference:

```powershell
python -B -m src.eval.contriever_header_diagnostic --run-inference --model-snapshot $snapshotPath --snapshot-manifest $trustedManifestPath --prior-dir $bm25Path --prior-dir $bm25HeaderPath --out-dir results/smoke_diagnostics/contriever_header_controls_v1 --repeat-check
```

The repeat check is always enforced. There is no automatic inference mode or
experimental fixture-score mode. Tests inject clearly artificial bookkeeping
fixtures internally; those establish no empirical model result. Approval of the
implementation does not mean a real-model experiment has been executed.
