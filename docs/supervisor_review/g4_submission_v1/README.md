# G4 supervisor-review submission v1

Date: 2026-11-05. Status: PRE-APPROVAL ENGINEERING REVIEW / CONDITIONAL_GO.
Published baseline: `de08db9712292d424e614c5e36e480ca16862128`, branch `master`.

This package describes synthetic engineering demonstrations and audit accounting,
not an approved benchmark or real experimental findings. Scientific judge validation
is BLOCKED; Week 6 main attacks are NOT AUTHORIZED. All fourteen decisions remain
UNRECORDED. No independent technical acceptance is asserted.

Start with the [submission index](submission_index.md), [engineering evidence](engineering_verification_summary.md),
[provisional coverage matrix](correction_coverage_matrix.csv), and [decision request](supervisor_decision_request.md).
The authentic original review package and November 3 correction document are both
MISSING locally. Authoritative coverage is INCOMPLETE. This package does not
reconstruct either missing source; prior separate text transmission is a researcher
report, not authenticated acceptance.

[Integration qualifications](integration_limitations.md) distinguish static schema
compatibility from runtime, model-token visibility and authorized execution.
[Dependencies](reproducibility_dependencies.md) describe the non-self-contained
reproduction requirements and authentic-document incorporation procedure.

The [exact publication classification](publication_allowlist.csv) enumerates all
185 baseline paths plus 13 new G4 files. Of 198 paths, 171 are YES_PROPOSED,
25 remain restricted, one transition draft is excluded and the real FreshQA ID
inventory is held for data-membership review. YES_PROPOSED is not publication,
staging or scientific approval. Review all content flags before any submission.

The [attributes proposal](gitattributes.proposed) applies only in an isolated test.
It is NOT installed in the project. [Validation results](publication_validation.json)
and [package hashes](sha256.json) record raw-byte checks. The two additional files
are justified: [source inventory](source_inventory.json) binds all 185 G3 baseline
paths, and [validator](validate_submission.py) reproduces local checks without any
backend execution. Hashes bind bytes; they do not authenticate evidence or reviewers.

Reverify the sealed package with:
`python -B docs/supervisor_review/g4_submission_v1/validate_submission.py`

This verifier writes only to a newly allocated OS-temp Git repository. It creates
no index or commit and performs no network operation. The initial `--record` form
writes only this new package's validation and hash files; sealed packages reject it.
Future changes require a new version. No staging, commit or push is authorized.
