# P1-C3: proposed transfer, dataset roles and resource feasibility

Status: DEVELOPMENT ONLY / NOT APPROVED. Baseline
`de08db9712292d424e614c5e36e480ca16862128`. No model downloads, inference,
held-out outcome analysis, case selection, scientific decisions or approvals.
The fourteen existing decisions remain UNRECORDED. Runtime measurements and GPU
availability are UNKNOWN. All quantities below are inventory counts or formulas,
not attack success rates or evidence of statistical adequacy.

## Primary generator and proposed transfer candidates

The primary configuration is Mistral-7B-Instruct-v0.2 at
`63a8b081895390a26e140280378bc85ec8bce07a`, 4-bit bitsandbytes, a float16 model
dtype argument, greedy decoding and 64 new tokens. The bitsandbytes 4-bit compute
dtype is not explicitly set; it must not be inferred from the model dtype.
The existing generator loader uses
AutoTokenizer/AutoModelForCausalLM and a model-specific chat template. Its docstring
mentions Kaggle T4; that is not evidence of currently available GPU hardware.

| Candidate | Access and interface evidence | Proposed disposition |
| --- | --- | --- |
| `Qwen/Qwen2.5-7B-Instruct` | Qwen2.5 family, 7.61B parameters, Apache-2.0 per official model card; Transformers and model-specific chat-template interface | Conditional first choice for transfer feasibility review |
| `meta-llama/Llama-3.1-8B-Instruct` | Llama 3.1 family, approximately 8B; gated HF access and custom Community License/use policy; Transformers chat interface | Alternative pending access and license acceptance |

Both are different families from Mistral. Exact revisions remain UNKNOWN; none
has been approved or fetched. Qwen is a conditional preference because its
published interface fits the existing causal-LM approach and has fewer access
constraints, not because local execution or GPU fit has been demonstrated.
Official sources consulted 2026-11-04:
[Qwen model card](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct),
[Llama model card](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct), and
[Transformers quantization documentation](https://huggingface.co/docs/transformers/quantization/bitsandbytes).
These mutable pages are not immutable revision manifests; card facts are
summarized in `external_sources.json` without inventing repository SHAs.

Raw weight-storage arithmetic is `parameters * bits / 8 / 2^30` GiB. For Qwen,
approximately 14.18 GiB at 16-bit or 3.54 GiB at idealized 4-bit; for Llama,
14.90/3.73 GiB respectively. These exclude unquantized layers, quantization
scales, buffers, allocator fragmentation, activations and KV cache. They are not
peak-VRAM requirements or promises of fit on a 4/8/16 GiB card. Additional KV
storage is approximately `2 * layers * KV_heads * head_dimension * batch_size *
sequence_length * cache_bytes`; actual configuration/cache dtype must be verified.
Dense-model prefill/decode cost scales with parameter and token counts, with
additional sequence-length-dependent attention work. Seconds/token, peak GPU/host
memory, setup/offload time and usable context are UNKNOWN until an authorized
development pilot measures them.

Proposed 4-bit loading may reduce weight footprint; it is not required if future
hardware supports a higher precision configuration. The exact quantizer,
compute dtype, device mapping, software versions and hardware need separate
pinning and compatibility checks. No dependency updates occur here. Greedy
`do_sample=False` is supported by the generation API, but does not guarantee
bitwise reproducibility across kernels/hardware. Model-specific templates,
special tokens, EOS/pad settings, implicit system prompts, context limits and
normalization must be audited separately. Keep the same user instructions and
evidence bodies; do not reuse Mistral token IDs or assume equivalent chat overhead.
The current observer's Mistral revision guard intentionally does not authorize
either transfer model. An explicit adapter and real-tokenizer verification are
still needed. Record immutable model/tokenizer revisions and file digests,
prompt/config hashes, quantization, runtime, seeds, selected contexts and final
input traces before any eventual transfer evaluation.

## Three proposed dataset roles and local evidence

The deterministic inventory reads question/evidence files only, not generated
answers or historical outcome summaries. It hashes all inventoried artifacts.

| Dataset | Proposed purpose | Verified local coverage and limitations |
| --- | --- | --- |
| StreamingQA | Primary temporal poisoning | Fixed review frame 400: 200 recent/200 past; 390 reconstructed evidence cases and ten source-year out-of-scope cases; zero independently accepted members. Existing clean chunked pilot pool has 100 questions and 2,069 candidate occurrences, not a frozen 400-question benchmark. |
| FreshQA | Independent temporal/factual robustness | 500 preprocessed questions; 492 source-fetch records, 470 successful nonempty texts and 22 failed fetches. Only 22 records carry a source date. Current pool has 474 questions and 9,480 candidate occurrences. Full evidence completeness is not established. |
| TriviaQA | Static control | 100 local clean pools, 491 candidate occurrences; no explicit stable QA IDs in these records. Suitable only as a proposed static/factual comparison after identity/provenance review. |

FreshQA's current YAML describes 477 questions but the artifact has 474. More
seriously, current pool candidates are strings with a parallel `candidate_metadata`
array; the current builder and runner expect dictionary candidates. These are
verified compatibility discrepancies, not permission to reconstruct the missing
three records or silently convert a frozen file. Metadata source flags and dates
are inventoried separately from candidate dictionaries; zero dictionary flags
must not be misreported as zero evidence coverage. Fetch success/text availability
does not authenticate original source content. Date metadata may be published or
modified date; retrieval time is not publication time. Effective-year end-of-year
conversion and snapshot-time fallback in the pool builder need scientific review.
Future repairs should create a separately versioned derived artifact with a
traceable migration and reconciliation, preserving this snapshot.

FreshQA preprocessing preserves answer aliases and fact/false-premise fields,
but its time-dependent answer states and evidence support require adjudication.
Its historical FreshEval judge uses the same Mistral family as generation;
that does not establish independent claim-specific v2 validation or transfer-judge
validity. Existing evaluation/development use creates leakage/exposure concerns;
an independent dataset label alone does not make it an untouched holdout.

StreamingQA source configuration documents reconstruction after the original
interactive session. B1/B2 distinguish traceability from authentication, original
answers from derived question-time proposals, and recorded activity from approved
exclusion. The 300 priority cases are not accepted members. Original aliases must
remain unchanged while derived keys and temporal support receive independent
review. Clean pilot pools and source-ID bindings must not be generalized to the
400 review cases without explicit reconciliation.

TriviaQA is static here: no authenticated publication-time framework, temporal
intent labels or question-time answer adjudication is established. Local records
contain gold/aliases and text candidates but no explicit upstream question IDs;
restore authoritative identity/provenance through traceable derivation before
cross-dataset claims. Public benchmark pretraining overlap and prior project
baseline exposure remain possible. A cached Natural Questions dataset is not a
verified project pool or approved alternative; no suitable processed NQ artifact
or reviewed loader is established by this inventory. Choose TriviaQA provisionally
for engineering reuse, not a simultaneous fourth dataset.

False-claim header controls and direct conflicting-evidence RQ3 are mechanically
portable only after reviewed false/correct states and source identity binding.
Stale amplification requires question-specific temporal intent and valid older
evidence; fabricated-fresh, date shifts and duplication need their own family
eligibility and negative controls. Static controls can test wording/order/date-cue
susceptibility but cannot establish real temporal benchmark performance. All
dataset roles are proposed and exploratory pending the requisite approvals; no
confirmatory claim is currently authorized.

## STRONG scope versus engineering and scientific readiness

No verbatim authoritative STRONG-scope specification is available in this repo;
the original supervisor package was sent separately. This checklist addresses
the stronger scope explicitly requested in this checkpoint, without pretending
to recover unseen requirements.

Implemented: E1-E4 text retrieval interfaces, shared generator assembly, synthetic
matched controls, eight-cell generator-isolated factorials, conservative judge
code, exposure-policy alternatives and proposed clustered statistical calculations.
Engineering tests alone approve none of these scientifically.

Additional data/reconciliation: authenticated sources, missing/failed FreshQA
snapshots and schema alignment, stable static-control identities, per-question
temporal semantics and reviewed original/derived/false keys. Additional execution:
authorized offline tokenizer checks, GPU fit/latency/memory pilots, cross-family
input adapters, then explicitly authorized evaluation. Additional approval:
exposure/sampling, populations/estimands, endpoints, multiplicity, eligibility,
rubric and blinded judge validation. Accepted sample size, statistical power,
transfer generalization and required GPU-hours cannot yet be established.

## Resource formulas and prevention of double counting

Per dataset let Q be hypothetical questions, R retrieval systems, F disjoint
attack families, M matched arms per family, C additional disjoint negative-control
variants, Q3 direct-factorial cases, G generator families, Sg generation repeats,
Sr retrieval/context repeats, E evaluation passes and J judge passes.

* Retrieval/context work units: `Q * R * (1 + F*M + C) * Sr`.
* End-to-end generation requests: retrieval units times `G*Sg`.
* Direct RQ3 requests: `Q3 * 8 * G * Sg` (no R/F/M/Sr multiplier).
* Total generated answers: sum of those two generation workloads.
* Evaluator/judge work units: total answers times E/J respectively.

Clean retrieval and answers are counted once per question/system/context seed,
not once per family. Retrieval is shared across generators and generation repeats
only if its data/config/context hashes are identical and retrieval is not generator-
conditioned. Repeated retrieval seeds mean distinct contexts; duplicate contexts
should be deduplicated before execution. RQ3 is a separately declared experiment,
not another retrieval condition. Negative controls already present in matched
arms must not be counted again as C. Count-only inputs cannot detect semantic
overlap: eventual execution requires an explicit unique workload-key registry.
Likewise, deterministic duplicate requests need a declared purpose, not automatic
scientific replication claims. No scenario selects question IDs.

Optional explicit retrieval/generation variant-group keys can collapse reusable
requests separately: replace `(1+F*M+C)` with the corresponding number of distinct
groups. The planner rejects generation reuse across different retrieval-context
groups. Group declarations are planning assumptions, not proof of equality;
actual reuse must verify complete input/config hashes. This also permits reuse
for date-blind metadata-only variants when their text inputs match. Defaults count
all variants separately and are request-slot upper bounds until deduplication is
established. Cross-RQ3/end-to-end duplicate prompts likewise need reconciliation
in the eventual exact workload registry; the count-only scenario cannot prove
those disjoint. No duplicated request is claimed to be a measured new run.

Serial cost formula: `Ngen*tgen + Nret*tret + Njudge*tjudge`, excluding setup,
evaluation, downloads, storage and concurrency. Unknown nonzero-stage durations
propagate UNKNOWN. Rule-based judging consumes different resources from LLM
judging; J counts passes, not necessarily GPU calls. Separate per-model/dataset/
length/quantization pilot rates are needed before replacing a scalar average.
Token cost is `sum(input_tokens + output_tokens)` by stage/model, UNKNOWN without
verified tokenizer lengths and output distributions. Sequential model execution
avoids summing all model weights into simultaneous VRAM; peak memory is the
maximum measured co-resident stage footprint, still UNKNOWN.

The two-question arithmetic fixture gives 24 retrieval units, 48 end-to-end
generations and 32 RQ3 generations = 80 answers. The illustrative 300-question,
four-system, five-family, two-arm, two-negative-control, two-generator scenario
gives 15,600 retrieval units plus 31,200 end-to-end and 4,800 RQ3 generations =
36,000 answers. This is not an approved 300-case sample or balanced eligibility
claim. Separate three-dataset 100-question illustrations are hypothetical input
counts, not established FreshQA/static attack coverage. No runtime is measured.

## Ordered gates, reproducibility and remaining authority

Gate records remain UNRECORDED: evidence/key adjudication; exposure/sampling
policy; statistical protocol; exact backend-input verification; independent judge
validation; benchmark/protocol freeze with approved hashes; explicit Week 6
authorization. Freeze depends on the preceding approvals, and execution depends
on all gates. No engineering test result can satisfy an external approval field.

```powershell
python -B -m src.eval.transfer_scope_audit --output audits/p1_c3_v1
python -B -m pytest -p no:cacheprovider tests/test_transfer_scope_plan.py -q
```

The audit verifies the entire prior chain including P1-C1 before writing, preserves
all earlier artifacts, and emits dataset coverage/hashes, candidate and scope
feasibility, configurable resource scenarios, pending gates, external references,
source inventory, validation and checksum records. Output is canonical UTF-8/LF;
differing existing reports are rejected. No credentials or environment secrets
are recorded. Public documentation checks are not model downloads. No stage,
commit, push, inference, benchmark selection or scientific approval occurs.
