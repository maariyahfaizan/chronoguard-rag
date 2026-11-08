# Week 4 v2 experiment adapter

This is an engineering adapter, not scientific authorization. Historical E1–E4
scripts, evaluator behavior, data, and results are untouched. No full experiment
is authorized by this implementation.

## No-model synthetic smoke

From the repository root:

```powershell
python -B -m pytest tests/test_streamingqa_v2_experiment.py -k "synthetic_smoke or manifest_rejection" -q
```

This builds a schema-compliant synthetic package in pytest temporary storage,
serializes and verifies it with A14, and exercises E1–E4 orchestration with
explicit test doubles. It does not claim model quality, tokenizer verification,
or scientific retrieval validity. It checks occurrence bindings, duplicated
canonical identities, immutable inputs, output isolation, and metric suppression.

Optional read-only real package validation (no models):

```powershell
python -B scripts/run_streamingqa_v2.py data/processed/week4_v2/a15_full_roundtrip_v1
```

The default external digest is
`54bcdb17b8ba086c2a1a2208e0621bdac6713ded619b414a02f8c04b4424ba1a`.
An explicit `--expected-manifest-sha256` supports synthetic packages and other
independently trusted packages; it is never inferred from package contents.
A14 rejects byte, schema, source, ordering, or implementation reconstruction
mismatches. Missing packages fail; there is no historical-data fallback.

## Execution contract

The runner requires explicit `--execute`, `--system E1|E2|E3|E4`, and a unique
`--run-name` to run models. Do not use that option without separate experiment
authorization. Optional `--limit` selects a prefix after complete verification.
Outputs are confined to `results/week4_v2/<run-name>`; existing directories are
rejected. Failures after the initial metadata write retain an INCOMPLETE run
receipt; a failure during that first serialization can leave an empty directory.

### Runtime metadata failure and safe retry

The final `run.json` write previously rejected `runtime.torch`: PyTorch's
`torch.__version__` is a `torch.torch_version.TorchVersion` (a `str` subclass),
while A14 permits only exact built-in JSON types. The adapter now explicitly
records that field as a plain string via `str(torch.__version__)`, preserving
the version text, including any build suffix. The strict serializer is unchanged.

The run directory is created before the initial receipt is encoded. For this
final-write failure, it already contains the initial INCOMPLETE `run.json`,
`answers.jsonl`, and `summary.json`; it must not be treated as a completed run.
Other failures can leave fewer files or partial answers. There is no automatic
cleanup or resume, and reusing the name raises `FileExistsError`.

Preserve the failed directory and its traceback. Inspect its receipt and files
read-only, then, when execution is authorized, retry the same package, external
manifest digest, system, and limit with a fresh unused run name (for example,
append `_retry1` to the original name). Keep the old artifacts for comparison;
do not delete, overwrite, or move them to make the original name reusable.
Confirm the retry's `run.json` says `COMPLETE` before using its outputs.

The adapter reads real keys from A9/A14, preserves the full envelope, and feeds
the same ordered `child_text` list to every retrieval path. Indices bind to
`child_occurrence_id`; canonical IDs and identical text never collapse occurrences.
E3/E4 use the existing index-keyed RRF; E4 uses the existing BGE reranker.
Configuration comes from `streamingqa_eval_config.yaml`, with revisions from
`model_revisions.yaml`. These pins cannot establish historical Week 4 revisions,
which were not recorded. Shared generation retains 4-bit Mistral, greedy
64-token decoding, and the 1500-character prompt cap. Unsupported generation
configuration changes fail closed. Seeds are recorded and applied; deterministic
GPU execution is not claimed.

Answer EM and alias F1 call the answer-only metric functions. The old
`evaluate_query` is never called. All retrieval relevance and temporal metrics
are explicitly unavailable, with zero eligible denominator and an omission
reason. Summary denominators count eligible questions. No annotation artifact
interface is implemented: even separately approved annotations require a future
reviewed integration before these metrics can become eligible. Parent source
flags, historical lexical gold, dates, and authentication never supply child
labels. Chronology and authentication are preserved separately; future-dated
and unauthenticated children remain in the pool.

A16's content counts exclude special tokens. Its 71 children over 320 with two
special tokens remain below 512; this adapter neither rewrites A15 nor imposes
a new 320-token rejection. Joint query/passage truncation remains a model
interface limitation and requires runtime auditing before scientific reporting.

Model-backed execution, GPU behavior, actual tokenizer truncation, and answer
quality are not covered by the no-model smoke. All records retain NOT_GRANTED
scientific status and the source execution-authorization state.
