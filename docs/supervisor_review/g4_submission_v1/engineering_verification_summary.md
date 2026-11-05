# Engineering verification and G3 baseline

Verified evidence: Git HEAD is `de08db9712292d424e614c5e36e480ca16862128`, branch
master. At G4 entry the tracked working tree and index were unchanged. All 185
untracked paths matched the G3 sorted path-to-raw-SHA-256 digest:
`3693d834883ad55f407dd9133fa123e527244f69f22d89bda07d3a98d256ba5e`.
The [inventory](source_inventory.json) records every path/hash/size. This is a
reconstructed inventory from current bytes verified against G3's reported digest,
not an authentic supervisor document or a newly committed candidate.

G1; P0-B1/B2/C1; P1-A1/A2/B1/C1/C3; and G2-I1 through I7 manifests and sources
verify. The published judge candidate's 23 files match raw hashes. All 279 protected
repository files and 56 recovery-project files match their prior inventories;
143 source inputs verify. Original keys, evidence, Week 4/5 artifacts, prior audits,
P0-A5 decisions, project attributes and historical runners are unchanged.

G3 read-only joins verified two G2-I1 pool rows -> eight G2-I2 pairs -> sixteen
requests -> sixteen G2-I3 context traces. Separately, sixteen P1-B1 factorial cells
-> sixteen G2-I4 exports -> sixteen G2-I5 alias-bound records -> sixteen unchanged
G2-I7 unobserved source projections. G2-I7 also has eight separate fictional label
descriptors, not additional observations. FreshQA is a separate four-fixture branch.
Matching body hashes across branches do not establish question identity.

## Recorded test evidence, not tests rerun by G4

| Checkpoint | Recorded command / scope | Recorded outcome |
|---|---|---|
| P0-A8 | `python -B -m pytest -p no:cacheprovider tests/test_answer_judge.py tests/test_answer_judge_v2.py -q` | 252 passed; published judge revision p0_a8_v2_repair_3 |
| G2-I1 | Adapter cases in checksum-bound regression; exact command in audit validation | 47 adapter cases; broad historical run 774 passed and 167 subtests |
| G2-I2 | Focused request tests; exact commands in audit validation | 30 passed in 20.25s; narrower regression 616 passed in 71.12s |
| G2-I3 | `python -B scripts/run_g2_i3_no_execution_tests.py` | 33 passed in 2.07s |
| G2-I4 | `python -B scripts/validate_g2_i4_no_execution.py` | 35 passed in 6.78s |
| G2-I5 | `python -B scripts/validate_g2_i5_no_execution.py` | 34 passed in 7.50s |
| G2-I6 | `python -B scripts/validate_g2_i6_no_execution.py` | 40 passed in 7.75s |
| G2-I7 | `python -B scripts/validate_g2_i7_no_execution.py` | 67 passed in 17.03s |

Historical broad G2-I2 testing included toy BM25 retrieval contrary to that
checkpoint's restriction. It remains a disclosed deviation, not evidence of a
respected no-execution boundary. Later explicit guarded allowlists are distinct.
Do not rerun historical broad commands under this package's restrictions.

G4 runs only hash, path/content classification, link/status and isolated Git byte
checks. No test suite, adapters, retrieval, generation, judging or estimators run.
Prior integrity definitions are reused only for hashing/static schema inspection;
model-bearing runners and experiment entrypoints are not imported.

## Bounded readiness

| Contract | Engineering boundary | Real scientific/runtime use |
|---|---|---|
| A | Tested fictional source-to-pool conversion | PARTIAL: authenticated authority provider absent |
| B | STRUCTURAL_ONLY: request signatures and static context | No executable dispatcher or actual retrieval/context selection |
| C | Tested explicit eight-cell static export | Approved cases and backend verification absent |
| D | STRUCTURAL_ONLY: reversible synthetic alias projection | Real-ID analysis and approved observed outcomes absent |
| E | Tested fictional strings-to-dictionaries | Real conversion disabled; membership/metadata review pending |
| F | STRUCTURAL_ONLY: proposed outcome mapping and blocking gate | Replay, validation, approved keys/policies absent |

G3 disposition was CONDITIONAL_GO for preparing a supervisor-review submission,
not permission to stage, execute or claim acceptance. Its authoritative coverage
was incomplete because both source documents were missing; that remains true here.
For current G4 checks, inspect [publication validation](publication_validation.json).
