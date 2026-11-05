# G2-I3: non-executing synthetic request-to-context traces

Scope: SYNTHETIC_ONLY / NOT_AUTHORIZED_FOR_EXECUTION. No retrieval (including
synthetic BM25), model loading, generator inference, network, main attacks or
real benchmark conversion. Prior checkpoints, historical runners, frozen inputs
and fourteen UNRECORDED scientific decisions are preserved.

## Actual assembly boundary

StreamingQA runners obtain ranked indices/texts, then pass retrieved passage
strings in their returned order to build_prompt and generate_answer. G2-I3 does
not execute the ranking or those runners. It uses the explicit manual synthetic
selection [0,1] in original candidate order for both arms. This is a conditional
trace of that plan, not an observed retrieval result or actual context selection.

The existing generation module imports Transformers and Torch at module scope,
so it must not be imported here. Only its hash-verified truncate_passage and
build_prompt AST definitions are reused. Their calls are restricted to slicing,
string joining and the known truncate helper. No load_model or generate_answer
definition is executed. Actual behavior: each passage is text[:1500], context is
joined with two newlines, and the same instruction/question/answer template is
used. Python character slicing is not token truncation. UTF-8 bytes and Unicode
code-point lengths/hashes are recorded separately.

generate_answer would next wrap this prompt in a user message, apply the model's
chat template and call model.generate. None of those steps executes here.
There is no production whole-context or whole-prompt character cap. Optional
audit caps are labeled synthetic negative-test fault injection; they are not
passed off as production behavior. Faulted traces are not writable as normal
trace outputs. Complete-body presence is checked at its exact source span in
both assembled context and prompt, not an unrelated substring in instructions.

## Four different readiness claims

| Layer | Evidence/status |
| --- | --- |
| Static request compatibility | G2-I2 pool fields and keyword templates checked against existing interfaces; no executed runner |
| Context assembly compatibility | This adapter reuses verified pure helpers for explicit synthetic selection, with exact text/span/hash checks |
| Actual tokenizer visibility | UNKNOWN: no verified generator tokenizer, chat-template IDs, token-span or actual model-input trace |
| Authorized execution readiness | BLOCKED: no dispatch, real admission or Week 6 authorization; independent scientific gates remain unrecorded |

Passing context tests establishes neither actual retrieval behavior nor receipt
by a model. No token counts, ASR, scientific outcomes or judgments are generated.

## Registration and paired invariants

Only the exact pinned G2-I2 request-pair artifact is accepted, bound to its
checksum manifest and source hashes. Real IDs, altered condition/request hashes,
body/header changes, candidate order changes, metadata/date drift and altered
settings are rejected even if a caller recalculates hashes. Trace IDs bind the
original request digest, explicit selection, fault caps and trace schema version
chronoguard.request-context-trace/v1. Duplicate or modified traces fail replay.

Each normal trace records exact candidate/selected document order, original
request/pair/condition IDs, selected rendered text and plain evidence bodies,
header, full context and prompt, user-message content, UTF-8 text hashes,
configured budgets and exact retained/body spans. Shared binding hashes verify
candidate identities/dates/metadata, answers/aliases, placement and budgets,
alongside the existing header-only request proof and configuration digest.
Condition IDs and request hashes differ intentionally; payload invariants do not.
Truncation faults report missing claims and pair asymmetry explicitly.

## Reviewed no-execution test boundary

The only allowed test file is tests/g2_i3/test_context_trace_adapter.py.
Before running, its complete source, imports and fixtures were inspected along
with the launcher, trace module, boundary implementation and existing prompt
helpers. tests/conftest.py was inspected (path setup only) but is not loaded.
No old test modules or broad repository suite are collected.

Run only:

```powershell
python -B scripts/run_g2_i3_no_execution_tests.py
```

The launcher statically checks test imports/call names; disables external pytest
plugins, inherited configuration and conftest; and uses an OS-temporary test
directory. Only its reviewed health-check plugin is enabled explicitly. The
boundary denies retrieval/model-bearing imports, forbidden function entry and
network/process audit events before operation bodies. It refuses preloaded
prohibited backends. Pre-collection self-checks must pass, health checks surround
each test, and maxfail=1 stops on unexpected failure. This is defense in depth for
reviewed code, not an adversarial Python sandbox.

Negative tests invoke inert, synthetic tripwires with forbidden operation names,
or emit audit events directly; they never import real retrieval/model modules,
open network connections or execute historical attacks. Expected profile-denial
exceptions clear Python's profile callback; the reviewed probe finally block
rearms it before returning. Unexpected denials outside probes fail the run.

Initial development checks exposed overly broad rejection of the pure prompt
comprehension and of the test controller, plus profile reset after a denial.
Those checks failed without any actual retrieval/model/network operation. The
accepted final run narrowly permits those reviewed pure paths, adds preflight
self-checks and fail-fast health checks, and verifies the guard remains active.
The initial failures are retained as facts in execution_boundary_validation.json;
they are not represented as successful boundary validation.

## Outputs, safety and reproduction

```powershell
python -B -m src.eval.request_context_traces --output audits/g2_i3_v1/context_traces.jsonl
```

The CLI installs the boundary before assembling/writing traces. It accepts no
real request path or execution option. The writer only creates new JSONL files
under the literal audits/g2_i3_v1 directory; production/prior paths, symlink
redirection and existing destinations are rejected. Reproduction uses another
filename under that root and compares hashes. All output is canonical UTF-8/LF.
Source inventory, invariant/boundary validation, integrity and checksum records
bind this candidate. G1's historical publication/attributes proposal is not
silently expanded to include these new files.

Prerequisites: exact G1/G2-I1/I2 and earlier audit hashes, immutable helper source,
and authorized access to the prior external integrity inputs. Byte hashes do not
authenticate upstream evidence or reviewers. Scientific validation, real keys,
tokenizer verification and explicit Week 6 authorization remain outstanding.
