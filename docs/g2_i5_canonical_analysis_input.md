# G2-I5: reversible synthetic identity compatibility and outcome gates

Status: SYNTHETIC_ONLY / NOT_AUTHORIZED_FOR_EXECUTION. This checkpoint validates
structure, not outcomes or estimands. No retrieval, generation, judging, numerical
estimation, network, benchmark execution or scientific approval occurs. All prior
artifacts and fourteen UNRECORDED decisions remain unchanged.

## Actual analyzer requirements

P1-C1 synthetic_analysis.validate(frame, rows) hardcodes a synthetic-stat-* prefix
for frame question IDs and requires row IDs to belong to that frame. It has no
namespace override or canonical-ID interface. This is a fictional-fixture safety
restriction, not a mathematical requirement of paired/factorial estimands: the
estimators group by exact question identity and condition/family keys, rather
than derive meaning from the prefix. Historical source is not modified.

G2-I4 correctly retained canonical synthetic-smoke-* construction IDs. Passing
them directly to that validator fails. G2-I5 therefore introduces an EXPLICIT,
reversible synthetic compatibility alias. It does not silently rename source
records or infer identity equivalence from text, order, matching answers or hashes.
If a future approved analyzer accepts canonical IDs, that interface should be
preferred through a separately versioned contract.

## Versioned identity contract

Input bundle version: chronoguard.canonical-analysis-input/v1.
Map version: chronoguard.synthetic-rq3-identity-map/v1.

For each registered canonical question, the map records its eight original cell
IDs, analysis conditions, source-construction hashes, G2-I4 export-record hashes,
and context/prompt hashes. The sorted cell binding list has a derived block hash.
There is no singular question-level construction record in the input, so this
derived hash is explicitly not described as an original upstream record hash.

The compatibility ID is synthetic-stat-g2-i5- followed by the full SHA-256 of the
map version, canonical ID and construction-block hash. A source/mapping revision
therefore requires a newly bound mapping artifact. Full-length hashes do not
remove the need for checks: duplicate canonical identities, alias collisions,
unregistered entries or altered bindings are rejected. Reverse lookup uses the
validated table, never attempts to reverse a hash or parse an ID substring.

Only the two exact registered G2-I4 fictional question blocks are accepted.
Namespace prefixes alone do not grant authority. Real records, rehashed altered
sources, missing/duplicate cells, wrong factors, prompt hashes or question pairing
fail authoritative replay. The alias is a transport key, not a new scientific QA
identity, adjudicated equivalence or approval credential.

## Canonical identity remains visible

Every exported condition retains question_id as the original canonical value,
adds canonical_question_id and analysis_question_id, and retains its original
cell ID, factors, source hashes, prompt/context and visibility fields. Only the
strict legacy analysis_projection.question_id uses the alias. The original
source_analysis_projection is retained alongside it. Both frame and condition
records are wrapped with canonical/analysis identities; no unbound bare legacy
row file is exported. Each map cell binding also carries its canonical identity.

The same alias is shared by all eight cells for one canonical question, and no
other question can share it. Frame membership, family=rq3, mapped condition,
unique cell keys and source provenance stay linked. Missing or extra blocks are
not silently dropped. Input row order does not influence mapping or export order.

## Actual structural compatibility without analyzer execution

The adapter hash-checks src/eval/synthetic_analysis.py and extracts only its
SCHEMA/RESOLVED literals and validate function through AST. It statically rejects
imports and unexpected calls in that definition. No estimator definitions,
statistical module imports or numerical calculations are executed. This is the
actual unchanged validation code, not a permissive replacement of its ID check.

Tests demonstrate direct canonical-prefix rejection and successful validation of
the explicit alias projection. This confirms structural compatibility only.
It does not override an estimator gate or establish eligibility, exposure,
statistical assumptions, scientific authority or readiness to analyze outcomes.

## Outcome and eligibility gates

All current records preserve:

* outcome_state = UNOBSERVED and projected outcome = MISSING;
* generator visibility = UNVERIFIED, actual visibility = UNKNOWN;
* execution status = NOT_AUTHORIZED_FOR_EXECUTION;
* frame eligibility = UNKNOWN and clean baseline = MISSING;
* analysis eligibility blocked for unobserved/unverified input.

No missing value becomes zero, incorrect, abstention or poison adoption.
require_estimator_ingestion first validates exact bundle/map provenance, then
raises NOT_ESTIMABLE for these unresolved gates. It never returns numerical rows
or invokes an estimator. Observed or real data is outside this immutable synthetic
profile; it cannot be authorized by changing flags. Existing analyzers are also
not wired to this artifact automatically. Manually bypassing wrapper checks is
not supported, and the Python guard is defense in depth rather than an adversarial
sandbox. No p-values, effect sizes, intervals or experimental conclusions appear.

## Guarded tests and output safety

```powershell
python -B scripts/validate_g2_i5_no_execution.py
python -B -m src.eval.canonical_analysis_input --output audits/g2_i5_v1/analysis_input.json
```

The only test module allowed is tests/g2_i5/test_canonical_analysis_input.py.
Source/imports, fixtures and launch code are reviewed before running. Existing
G2-I4 guard code is reused unchanged. Eight inert boundary self-checks precede
collection; forbidden-operation tests never run real retrieval, generation,
judging, estimator or network bodies. External plugins, project conftest/config
and broad suite discovery are disabled, with fail-fast and guard-health checks.
Only the reviewed legacy structural validator is permitted; full analyzer import
and numerical entrypoints remain blocked.

The writer creates only new JSON files inside the literal audits/g2_i5_v1 root.
Production/prior paths, escapes, symlink redirection and existing files fail.
Reproduction uses a new filename under that root and verifies hashes. Canonical
UTF-8/LF output is deterministic for unchanged inputs. G1's historical allowlist
and byte policy are not silently expanded. Authenticated real evidence/key review,
scientific protocols, tokenizer visibility, judge validation and Week 6 execution
authorization remain external blockers.
