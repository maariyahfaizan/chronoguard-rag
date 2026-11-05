# G1 v1: controlled consolidation and integration contract

PROPOSED ENGINEERING CONTRACT. No publication, execution or scientific approval.
Baseline: de08db9712292d424e614c5e36e480ca16862128, master. Existing files must
retain their exact bytes. G1 adds only this new directory. The eight prior
checkpoints remain immutable development artifacts.

## Publication boundary

`publication_allowlist.csv` is the exact path-level classification. It contains
the 89 G0 files plus nine new G1 deliverables. YES_PROPOSED is a prospective
engineering publication candidate, not authority to stage or publish. The 25 P0
audit files remain EXTERNAL_RESTRICTED_ARTIFACT. They include original questions,
keys and imported review assertions and require a separately controlled artifact
distribution decision. The transition draft is UNRELATED_EXCLUDED. No wildcard
staging, automatic publication or modification of original artifacts is permitted.

The 35 P1 audit files are publication candidates, subject to review. They do not
make the repository self-contained: their verification chain still needs the
restricted P0 artifacts and recovery project. Reproduction requires authorized
external access; absence of that access must stop verification, not relax hashes.

## Byte contract

The current tracked .gitattributes contains `*.jsonl text eol=lf`.
System Git config sets core.autocrlf=true. All 89 G0 files currently use LF.
The proposed file retains the existing rule and adds exact-path `-text` overrides
for the 72 proposed publication candidates. This preserves raw bytes rather than
normalizing them on add/checkout, and works for LF, CRLF and mixed-byte fixtures.
No broad extension rule or protected-file rule changes. Editing an audited file
later requires a new version/digest; -text does not make editor edits safe.

`gitattributes.proposed` is a complete candidate attributes file, NOT an applied
repository change. A future controlled submission needs separate approval for
the tracked `.gitattributes` patch as well as its file allowlist. Its contents
must match this proposal before staging. This checkpoint leaves the real index,
Git config, attributes, frozen files and prior untracked files unchanged.

The isolated test creates Git objects without staging or committing. It runs Git
clean filtering through hash-object --path and checkout filtering through
cat-file --filters, with core.autocrlf=true, and compares bytes. It then builds a
tree with mktree and materializes it with restore --source=<tree> --worktree,
checking every allowed file again. It also compares
protected-path attributes before/after, checks P1 audit hashes after roundtrip,
and checks synthetic schema cases. This exercises Git's checkout conversion
without creating a commit or an index. It is not a future full-clone
integration test. Temporary Git object directories contain no restricted P0 data.

## Integration specifications

`integration_contracts.json` contains six versioned proposed contracts, input and
output schemas, invariants, gates, provenance requirements, missing-state policy,
backward compatibility and synthetic positive/negative shape examples. The
validator checks a documented structural subset and invariant rules; it is not
a full JSON Schema implementation and does not implement any adapter. Passing
shape tests does not establish compatibility with existing runners or approval.

All ready-for-execution paths require independently recorded evidence/key,
exposure/sampling, statistical, backend-input, judge and execution authority,
bound to exact revisions and input hashes. Missing authority yields DRAFT_BLOCKED.
UNKNOWN, NOT_REVIEWED, MISSING, UNAVAILABLE, TRUNCATED and UNVERIFIED must remain
distinct. No unknown is coerced into false, unexposed, a timestamp or approval.

A: approved sidecars supplement the immutable B1 row; they never rewrite gold or
aliases. Derived question-time keys require exact independent approval. Candidate
identity and source lineage are preserved; no first-answer selection or implicit
primary-key creation. Unknown dates/keys are draft-only, never passed to strict
runner inputs. This contract is not a grant of eligibility to the 300 priorities.

B: authoritative base/pair replay, same settings, source IDs, target slots,
ordering and body hashes; only declared header/date interventions may differ.
Retrieval plans and selected context are separately logged. No visibility is
inferred from rank. Final tokenized input and exact backend identities are needed
before a verified-visible claim can be emitted. Historical constructors stay intact.

C: exactly eight direct-presentation cells, both evidence bodies in every cell,
two assigned date values swapped, fixed per-passage budgets, no retrieval. Preserve
source IDs and original body hashes. Assigned dates remain experimental cues.
Unknown token balancing stays UNVERIFIED, not equal. No inference occurs here.

D: name mapping is explicit: correct/incorrect newer-looking becomes
correct_newer/incorrect_newer; neutral/freshness and order labels are retained.
Keep canonical source QA IDs, and place construction cell IDs plus source hashes
in a separate binding table, not extra fields in the current strict analysis row.
The current analyzer accepts only synthetic-stat-* question IDs and cannot directly
consume synthetic-smoke-* construction IDs or real QA IDs. Do not silently rename
them to pass its guard. A separately reviewed analysis-schema revision supporting
canonical IDs is required. Incomplete cells or unverified input are NOT_ESTIMABLE;
never complete-case substitute. A type-correct proposal is not a working adapter.

E: legacy strings join only to equal-length metadata by explicit index; require
unique document IDs and exact text hashes. Dictionary inputs retain exact source
fields. Reject missing, duplicate, reordered or contradictory metadata. Preserve
all 474 actual records; do not invent the configured missing three. Source dates
remain distinct from retrieval times; unknown dates remain null with UNKNOWN basis.
The current runner's required non-null inputs may remain blocked. Normalized
outputs must be new derived artifacts with parent hashes, never replacements.

F: v2 rows must pass authoritative replay against independently loaded inputs and
exact rubric/implementation/key revisions. POISON_ADOPTED/CORRECT retain meaning;
NEEDS_REVIEW stays unresolved. OTHER_WRONG plus independently replayed
pure_abstention may map to ABSTAIN; empty_answer is explicitly MISSING under this
proposed policy. Other OTHER_WRONG stays OTHER_WRONG. This outcome policy needs
scientific approval; it is not current approved practice. Human resolution needs
authenticated review/adjudication sidecars; supplied names/hashes do not prove
authority. Exposures and construction status come from their own trace records,
never from the outcome label. Preserve raw label/reason and fingerprints in bindings.

## External dependencies and original package

`external_dependencies.json` records exact source paths/hashes, logical root
bindings, prior audit manifests, tokenizer inventories and unavailable authority.
Map repository and recovered roots explicitly on another machine; do not infer
files from filenames, regenerate evidence or replace unavailable models. Original
source-artifact hashes can be declared records without the historical bytes being
available. Traceable reconstruction is not original-source authentication.

The original `ChronoGuard_RAG_Supervisor_Review_Package.md` is MISSING locally,
including the requested docs/supervisor_review path. The researcher states that
the authentic package was transmitted to the professor separately by text. That
transmission is distinct from repository publication and does not establish
receipt of approval. An authentic researcher-supplied original is needed for
complete authoritative requirement mapping; no replacement is constructed.

## Validation and limits

Run `python -B docs/consolidation/g1_v1/validate_contracts.py --repo <repository>`.
The test writes only an isolated OS-temporary Git directory; no staging, commits,
model downloads, inference or project-file edits. Validation results distinguish
structural schema tests, byte filtering, actual source integrity and scientific
approval. No old test suite is rerun because its temporary-output fixtures would
write inside the project. All fourteen decisions remain UNRECORDED. Week 6 main
attacks and scientific judge validation remain blocked.
