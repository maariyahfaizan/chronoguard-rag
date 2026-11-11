# ChronoGuard-RAG Week 4 v2 baseline results

## 1. Executive Summary

This report documents the existing clean StreamingQA v2 baseline: four completed E1–E4 runs on the same frozen development frame of 100 questions. It separates answer scoring, mechanical timestamp chronology, and a bounded human relevance review. These are different measurements and cannot substitute for one another.

- **Answer generation:** E1–E4 Exact Match (EM) is 60%, 59%, 60%, and 61%; token F1 is 76.48%, 77.64%, 78.28%, and 79.34%, respectively. E4 has the highest observed scores; statistical superiority is not established.
- **Retrieval chronology:** the 2,000 final top-five slots contain 1,014 distinct question–child pairs. Of those pairs, 33 are future-dated under the supplied timestamps; 14 questions have exposure in at least one system. This is not proof of poisoning or invalid evidence.
- **Human-reviewed relevance:** the deliberately selected 100-pair pilot contains 49 RELEVANT, 45 NOT_RELEVANT, and 6 UNKNOWN judgments, with notes on every row. It remains a reviewed candidate without independent validation.
- **Unavailable retrieval metrics:** full-dataset Recall@5 and nDCG@5 remain unavailable. The pilot covers 327 retrieval slots (16.35%) and does not provide complete relevance judgments.

Sources are the completed `full_002` run summaries and answer records, the post-hoc chronology tables, and the reviewed annotation CSV identified below. Preparation of this report used read-only artifact checks; no experiments were rerun.

## 2. Research Objective and Scope

The clean, non-attacked baseline provides a reference for later controlled freshness-poisoning experiments involving retrieval, evidence selection, and answer generation. Week 4 v2 does not demonstrate a controlled poisoning attack or its causal effects. A future-dated passage in an unchanged pool is an exposure observation, not an injected attack.

The reporting population is the A15 fixed StreamingQA development frame and the four `week4_v2_e*_full_002` directories. `docs/week4_closure.md` describes an older baseline with different preprocessing, scores, and relevance assumptions. Its results must not be merged into this v2 report. FreshQA and TriviaQA results in that closure note are outside the present scope.

Existing receipts retain `scientific_approval: NOT_GRANTED`, `scientific_validation: NOT_VALIDATED`, and package execution authorization `NOT_AUTHORIZED_FOR_EXECUTION`. Completed engineering runs do not establish scientific approval or retrospectively resolve authorization. This documentation task grants no experiment or attack execution authorization.

## 3. Experimental Setup

### Frozen data and passage representation

The package is `data/processed/week4_v2/a15_full_roundtrip_v1/`. Its `manifest.json` identifies schema `streamingqa_week4_v2_1`, specification `streamingqa_week4_v2_spec_1`, identity version `streamingqa_identity_a9_v1`, and frame:

```text
sqa-frame-v2:39581d0523efee2705228755ca6c27cf754336c7adb7fdd4974fd61b3d4dfef6
```

The independently computed manifest SHA-256 is:

```text
54bcdb17b8ba086c2a1a2208e0621bdac6713ded619b414a02f8c04b4424ba1a
```

All four run receipts bind to this digest. All files enumerated by the package manifest were independently checked against their recorded byte hashes and matched.

The manifest and `pool.jsonl` describe 100 questions, 2,000 parent occurrences, and 2,072 child occurrences/canonical children. Each question has a fixed local candidate pool derived from its 20 parent occurrences; retrieval is over these supplied candidates, not a search of the complete external StreamingQA corpus. The preserved inputs are the control sample, raw evaluation archive, and parent pools under the package's `inputs/` directory. Question ordering follows the original sample order.

The package configuration specifies source-slice chunking (`streamingqa_source_slice_v2_1`), a 320-token content budget, requested overlap of 64 tokens, a 1,500-character limit, no normalization, and no tail merge. Retrieval uses the ordered `child_text` representation. Occurrences retain `child_occurrence_id` and `canonical_child_id`; duplicate occurrences are not silently collapsed. The manifest retains offline/unverified tokenizer construction status. `results/week4_v2/a16_tokenizer/asset_receipt.json` records local tokenizer asset hashes but explicitly reports no independent upstream verification. Neither receipt proves absence of runtime query/passage truncation.

### Models, retrieval, and generation

The following pins are recorded in each completed v2 `run.json` and in `configs/model_revisions.yaml`:

| Role | Model | Recorded revision |
|---|---|---|
| Generator, E1–E4 | `mistralai/Mistral-7B-Instruct-v0.2` | `63a8b081895390a26e140280378bc85ec8bce07a` |
| Dense retriever, E2–E4 | `facebook/contriever` | `2bd46a25019aeea091fd42d1f0fd4801675cf699` |
| Reranker, E4; construction tokenizer | `BAAI/bge-reranker-base` | `2cfc18c9415c912f9d8155881c133215df768a70` |

These are verifiable recorded configuration pins, not independent verification of loaded model weights. They do not establish the revisions used by the older Week 4 baseline, whose revisions were not recorded.

| System | Retrieval configuration | Final passages |
|---|---|---:|
| E1 — BM25 | `rank_bm25.BM25Okapi`, lexical retrieval | 5 |
| E2 — Contriever | Attention-mask mean pooling; dot-product similarity | 5 |
| E3 — Hybrid/RRF | BM25 and Contriever each request 20 candidates; reciprocal rank fusion with `rrf_k=60` | 5 |
| E4 — Hybrid/RRF + BGE reranker | Same candidate requests and RRF constant; 20 fused candidates requested, followed by query–passage cross-encoder reranking | 5 |

Candidate requests are bounded by the available local pool. The saved final records contain exactly five distinct child occurrences per question in every system. The dense and reranker interfaces describe a 512-token limit; joint query/passage truncation remains a limitation, not an independently audited runtime guarantee.

The v2 adapter reads `configs/streamingqa_eval_config.yaml` and the revision pins; `configs/streamingqa_week4_v2.yaml` describes construction rather than being the runner's evaluation configuration. The authoritative effective configuration is embedded in each `run.json`. The older input path, chunk statistics, and historical `results` mappings embedded inside the evaluation YAML are inherited configuration metadata; they are not the v2 input or v2 measurements. The v2 input is the manifest-bound A15 package and its per-answer `source_envelope`.

Generation records 4-bit quantization, greedy decoding (`do_sample=false`), a maximum of 64 new tokens, and the shared 1,500-character passage cap. The receipts record seed 42, Python 3.12.13, PyTorch 2.10.0+cu128, CUDA 12.8, and CUDA availability. The adapter applies Python and PyTorch seeds, including CUDA seeds. `deterministic_execution_verified` is false; GPU determinism, exact hardware identity, and a complete frozen runtime environment cannot be established from these receipts.

## 4. Answer Accuracy Results

Authoritative sources are `summary.json` in each completed `full_002` directory, checked by independently averaging the corresponding per-question `answers.jsonl` metric values. Each EM and F1 denominator is 100. All requested headline values match after rounding.

| System | Exact Match | Token F1 | Stored mean F1 |
|---|---:|---:|---:|
| E1 — BM25 | 60% | 76.48% | 0.7647959898246921 |
| E2 — Contriever | 59% | 77.64% | 0.7764082606560886 |
| E3 — Hybrid/RRF | 60% | 78.28% | 0.7828258067955847 |
| E4 — Hybrid + reranker | 61% | 79.34% | 0.7933593288256691 |

The adapter calls the answer-only `exact_match` and `f1_score` functions in `src/eval/metrics.py`, comparing generated answers with preserved gold answers/aliases. These are lexical answer scores against unreviewed aliases, not independent verification of factual correctness, passage relevance, source authority, or temporal validity. E4 has the highest observed EM and F1, but no appropriate significance analysis for these v2 results was located or performed. The small differences do not establish statistically significant superiority.

**Historical discrepancy:** `docs/week4_closure.md` gives older StreamingQA EM/F1 values of E1 0.620/0.781, E2 0.610/0.782, E3 0.590/0.770, and E4 0.590/0.776. These differ from the v2 run summaries above and refer to the older chunked baseline. Historical relevance metrics and statistical claims in that note are not evidence for v2 relevance or significance. Also, `week4_v2_e1_full_001/run.json` is `INCOMPLETE`; its presence alongside answer/summary files does not make it an eligible completed run.

## 5. Temporal Exposure Analysis

`scripts/week4_posthoc_analysis.py` defines the post-hoc rule: convert the preserved question Unix timestamp and raw child publication timestamp to UTC calendar dates, then mark FUTURE only when the publication date is later than the question date. Same-day ordering is not resolved by this rule.

Read-only reconstruction from the frozen pool and completed answer records matched `top5_retrieval_chronology.csv`, `temporal_exposure_by_system.csv`, and `posthoc_report.json`:

| System | Future-dated slots | Percentage of system slots |
|---|---:|---:|
| E1 | 13/500 | 2.6% |
| E2 | 18/500 | 3.6% |
| E3 | 16/500 | 3.2% |
| E4 | 12/500 | 2.4% |

Across systems there are 2,000 slots, 1,014 distinct question–child pairs, 33 distinct future-dated pairs, and 14 questions with future exposure in at least one system. Slot counts include repeated appearances of the same pair across systems; distinct-pair counts do not. All top-five slot timestamps are parseable in the saved analysis.

The separate A18 full-pool audit, `a18_chronology/chronology_report.json`, reports 89 future child occurrences among 2,072 candidates and 14 affected questions. This is a different denominator from the retrieved top-five union. A18 retains UNKNOWN temporal-validity labels and NOT_AUTHENTICATED source labels throughout; these labels are not changed by the post-hoc comparison.

These are mechanical comparisons of supplied timestamps, not independent publication-date verification or evidence-validity judgments. FUTURE does not establish maliciousness, causal poisoning, or an incorrect answer; PAST_OR_SAME_DAY does not establish valid evidence.

## 6. Human Relevance Annotation Pilot

The reporting source is `results/week4_v2/posthoc_analysis/annotation_pilot_reviewed_candidate_v2.csv`, checked directly rather than inferred from the QC summary:

| Review property | Verified result |
|---|---:|
| Distinct annotated question–child pairs | 100 |
| RELEVANT | 49 |
| NOT_RELEVANT | 45 |
| UNKNOWN | 6 |
| Rows with nonempty reviewer notes | 100 |

`docs/ChronoGuard_A17_Annotation_Protocol.md` instructs reviewers to read the question, gold answers, and selected child; judge whether the child independently supports a correct answer; avoid inheriting parent relevance or treating answer-string presence as sufficient; and keep chronology and source authority separate. UNKNOWN covers incomplete, ambiguous, contradictory, or unreliable evidence. The saved candidate's notes provide the evidence-based rationale; they do not independently authenticate the reviewer or annotation procedure.

The selection implementation in `scripts/week4_posthoc_analysis.py` includes all 33 future-dated pairs, then prioritizes cross-system overlap while spreading additional selections over questions, filling remaining positions by overlap priority if necessary. This is deliberate sampling, not random sampling. Shared retrieval hits can produce many annotated system slots from one annotation. The saved candidate labels all 33 future pairs NOT_RELEVANT, but the semantic judgments must be distinguished from their chronology flags; the selected sample cannot establish a general relationship between future dates and relevance.

`annotation_pilot_qc_summary_v2.json` records a targeted QC pass over rows 1, 4, 5, 6, 10, 18, 20, 27, 39, 44, 63, and 75, and claims label changes at rows 10, 18, 27, and 75. **Unresolved provenance discrepancy:** the saved prior annotated CSV (`bounded_100_item_annotation_pilot_annotated.csv`) and the reviewed candidate are byte-identical, with independently verified SHA-256:

```text
f2d58f512e9f1e2116972b06935876d46c50e1c3936250370ffc6c297f267209
```

The final 100 saved annotation labels and their counts (49 RELEVANT, 45 NOT_RELEVANT, 6 UNKNOWN) are verified. The four historical label changes at rows 10, 18, 27, and 75 cannot be independently reconstructed from the two saved CSVs; the QC summary's `source_sha256` matches both. This discrepancy does not invalidate the verified final label counts, but limits the auditability of the annotation revision history. The pilot remains single-reviewer and is not independently validated ground truth. No labels were altered or reconstructed for this report.

The pilot is a single-reviewer candidate. No independent second review, adjudication, or agreement statistic is established. The A17 protocol calls for independent double review of 30 selected calibration items, but completion evidence for that requirement was not located. The separate `a17_annotations/` calibration artifacts are not a substitute for validation of this later post-hoc pilot.

Gold-answer ambiguities remain unresolved. For example, UNKNOWN notes identify an October 2021 versus October 2012 outage mismatch (`eval-007296`), conflicting Cavaliers/Hawks aliases (`eval-027493`), and a garbled own-goal question with ill-fitting aliases (`eval-035142`). Other UNKNOWN judgments concern tentative or incomplete passage support. Neither the answer key nor these labels was silently repaired.

## 7. Exploratory Retrieval Relevance

The reviewed labels were joined to the saved final top-five occurrences using `(question_id, child_occurrence_id)`. For every matched pair, the frozen envelope's `canonical_question_id`, the child's `canonical_child_id`, and `child_text` were also checked against the annotation. Frozen `frame_id` and `question_order` bind the answer envelope to the pool; the saved chronology table's system/question/rank records were checked against the retrieved occurrence IDs. No join depended on answer strings, passage-text similarity, or assumed CSV row alignment.

| System | Annotated slots | Relevant | Not relevant | Unknown |
|---|---:|---:|---:|---:|
| E1 | 80 | 49 | 25 | 6 |
| E2 | 85 | 49 | 30 | 6 |
| E3 | 83 | 49 | 28 | 6 |
| E4 | 79 | 49 | 24 | 6 |

The reproduced totals are 327 of 2,000 slots annotated (16.35%) and 100 of 1,014 distinct pooled pairs annotated. Each annotated pair can contribute a slot in more than one system. UNKNOWN remains a separate category.

**These are counts within a deliberately selected annotated sample, not estimates of overall retrieval quality.** They must not be used to rank systems by relevance performance. The equal relevant counts reflect the selected overlap and do not establish equal corpus-level retrieval performance.

## 8. Unavailable Retrieval Metrics

Full-dataset Recall@5 and nDCG@5 are unavailable because the pilot does not provide complete relevance judgments for the pooled top-five results, and UNKNOWN cases remain unresolved. Missing labels cannot be treated as negative or discarded to manufacture a full-dataset metric. nDCG also needs defensible relevance grades and an ideal ranking under a defined evaluation universe.

Even complete judgments for the pooled top-five union would support only an explicitly defined pooled judged-set analysis. True corpus-wide recall requires a defensible relevant-document set across the declared retrieval universe, potentially including relevant items outside the retrieved union. Here the actual retrieval universe is each question's supplied candidate pool; recall over that pool would still not establish recall over the external corpus.

The v2 summaries explicitly store null values and zero eligible denominators for `recall_at_5`, `ndcg_at_5`, `valid_evidence_recall_at_5`, `time_valid_answer_accuracy`, and `fraction_top_5_violating`, with reason `No provenance-bound explicitly approved child annotations`. The exploratory chronology table is a separate mechanical analysis; it does not retroactively populate these suppressed evaluator metrics. No full-dataset Recall@5 or nDCG@5 is calculated here.

## 9. Threats to Validity

- **Limited coverage:** the annotated pairs and slots cover only part of the retrieved population, with UNKNOWN judgments retained.
- **Purposeful sampling and overlap bias:** future-dated items and shared hits were deliberately prioritized, so sample counts are unsuitable for population estimates or system ranking.
- **Single reviewer:** a targeted QC pass does not supply independent validation, inter-reviewer agreement, or adjudication; its change-history claim is also unreproducible from the saved versions.
- **Gold-answer ambiguity:** preserved aliases can contradict one another or the question; lexical answer scores are conditional on this unreviewed key.
- **Unverified dates:** raw publication timestamps and calendar-date comparisons cannot establish authentic publication history, authority, temporal validity, or poisoning.
- **Small development evaluation:** the fixed 100-question frame limits generalization; no significance testing for these v2 comparisons is established.
- **Different constructs:** answer correctness, passage relevance, temporal exposure, and source authenticity require separate evidence. A correct answer can coexist with weak retrieved evidence.
- **Baseline scope:** no controlled poisoning intervention or causal attack comparison is part of these baseline results.
- **Reproducibility limits:** recorded model pins do not independently attest loaded weights; GPU determinism and complete runtime reconstruction are unverified. Runtime truncation and preserved representation-review flags remain relevant limitations.

## 10. Reproducibility and Artifact Inventory

All paths below are repository-relative and were checked to exist. Directories are listed where several related files form the reporting unit.

| Artifact | Path | Reporting role |
|---|---|---|
| Frozen manifest | `data/processed/week4_v2/a15_full_roundtrip_v1/manifest.json` | Package identity, counts, file digests, status |
| Frozen child pools | `data/processed/week4_v2/a15_full_roundtrip_v1/pool.jsonl` | Question envelopes and candidate identities/text |
| Frozen construction configuration | `data/processed/week4_v2/a15_full_roundtrip_v1/configuration.yaml` | Package construction settings |
| Frozen control sample | `data/processed/week4_v2/a15_full_roundtrip_v1/inputs/streamingqa_control_sample.jsonl` | Sample frame input |
| Frozen raw evaluation input | `data/processed/week4_v2/a15_full_roundtrip_v1/inputs/streamingqa_eval.jsonl.gz` | Preserved raw input |
| Frozen parent pools | `data/processed/week4_v2/a15_full_roundtrip_v1/inputs/streamingqa_control_pools.jsonl` | Parent candidate source |
| E1 completed results | `results/week4_v2/week4_v2_e1_full_002/` | `run.json`, `summary.json`, `answers.jsonl` |
| E2 completed results | `results/week4_v2/week4_v2_e2_full_002/` | Same three authoritative files |
| E3 completed results | `results/week4_v2/week4_v2_e3_full_002/` | Same three authoritative files |
| E4 completed results | `results/week4_v2/week4_v2_e4_full_002/` | Same three authoritative files |
| Transfer inventory | `results/week4_v2/transfer_manifest.json` | Transferred file identities and provenance |
| A16 tokenizer receipt | `results/week4_v2/a16_tokenizer/asset_receipt.json` | Recorded tokenizer asset provenance limitations |
| A17 annotation protocol | `docs/ChronoGuard_A17_Annotation_Protocol.md` | Child relevance rubric and double-review requirement |
| A17 earlier calibration | `results/week4_v2/a17_annotations/` | `child_relevance_queue.csv`, `calibration_100.csv`, `calibration_100_provisional.csv` |
| A18 chronology | `results/week4_v2/a18_chronology/chronology_report.json` | Full-pool mechanical chronology |
| A18 future candidates | `results/week4_v2/a18_chronology/future_children.csv` | Full-pool future-occurrence detail |
| Post-hoc summary | `results/week4_v2/posthoc_analysis/posthoc_report.json` | Aggregate scope and chronology method |
| Slot chronology | `results/week4_v2/posthoc_analysis/top5_retrieval_chronology.csv` | System/question/rank/occurrence records |
| System exposure | `results/week4_v2/posthoc_analysis/temporal_exposure_by_system.csv` | Slot denominators and future counts |
| Question exposure | `results/week4_v2/posthoc_analysis/question_future_exposure.csv` | Cross-system question exposure |
| Pooled retrieval queue | `results/week4_v2/posthoc_analysis/pooled_top5_relevance_queue.csv` | Distinct retrieved question–child pairs |
| Selected unannotated pilot | `results/week4_v2/posthoc_analysis/bounded_100_item_annotation_pilot.csv` | Deliberate selection record |
| Prior annotated pilot | `results/week4_v2/posthoc_analysis/bounded_100_item_annotation_pilot_annotated.csv` | Saved comparison version, identical to candidate |
| Reviewed candidate | `results/week4_v2/posthoc_analysis/annotation_pilot_reviewed_candidate_v2.csv` | Reported labels and reviewer notes |
| QC summary | `results/week4_v2/posthoc_analysis/annotation_pilot_qc_summary_v2.json` | QC claims, cautions, and unresolved version discrepancy |
| Construction configuration | `configs/streamingqa_week4_v2.yaml` | Specification; not runner evaluation input |
| Evaluation configuration | `configs/streamingqa_eval_config.yaml` | Retrieval/generation settings; contains historical result mappings |
| Revision configuration | `configs/model_revisions.yaml` | Recorded model pins |
| Adapter documentation | `docs/streamingqa_v2_experiment.md` | Execution contract and limitations |
| Runner and adapter | `scripts/run_streamingqa_v2.py`; `src/eval/streamingqa_v2_experiment.py` | Package-bound orchestration and metric eligibility |
| Persistence and construction | `src/eval/streamingqa_v2_persistence.py`; `src/eval/chunk_streamingqa_pools_v2.py` | Package verification and construction implementation |
| Answer metrics | `src/eval/metrics.py` | EM and token F1 definitions |
| Post-hoc script | `scripts/week4_posthoc_analysis.py` | Chronology reconstruction and purposeful pilot selection |
| Historical baseline documentation | `docs/week4_closure.md`; `docs/week4_post_freeze_validation.md` | Earlier baseline context, not v2 result authority |

### Verification and missing evidence

The transfer manifest lists 31 files, all present. Its raw SHA-256 values match the frozen package and completed experiment artifacts. Seven text files have raw byte mismatches: `docs/streamingqa_v2_experiment.md`, `scripts/run_streamingqa_v2.py`, `src/eval/streamingqa_v2_experiment.py`, `src/generation/generate.py`, `src/retrieval/dense.py`, `src/retrieval/reranker.py`, and `tests/test_streamingqa_v2_experiment.py`. For each, replacing CRLF with LF in memory reproduces the transfer digest. This identifies a line-ending difference; raw byte equality must not be claimed. No file was normalized on disk.

The source transfer ZIP referenced by the post-hoc script/report is absent from the repository. Its recorded digest is therefore not presented as independently verified. The existing extracted pool and runs nevertheless permit the reported chronology and join checks without that ZIP. No standalone A15/A18 narrative document was located; the package manifest, adapter documentation, and A18 JSON/CSV audit supply the available evidence. Independent second-review/adjudication evidence, a recoverable pre-QC label-change version, and v2 significance-test output were not located. No absent evidence was reconstructed.

### Read-only reproduction of the headline tables

From the repository root, the following standard-library Python checks only read saved artifacts. They do not import model code, run retrieval/generation, write outputs, or compute unavailable relevance metrics. The stronger verification used in preparing this report additionally checked frozen envelope equality, candidate identity/text bindings, and timestamp-derived flags against the chronology table.

```python
import csv
import json
from collections import Counter
from pathlib import Path

root = Path(".")
post = root / "results/week4_v2/posthoc_analysis"

def read_csv(name):
    with (post / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

annotations = read_csv("annotation_pilot_reviewed_candidate_v2.csv")
labels = {(r["question_id"], r["child_occurrence_id"]):
          r["human_relevance_label"] for r in annotations}
assert len(annotations) == len(labels) == 100
assert all(r["reviewer_notes"].strip() for r in annotations)
assert Counter(labels.values()) == {
    "RELEVANT": 49, "NOT_RELEVANT": 45, "UNKNOWN": 6}

slots = read_csv("top5_retrieval_chronology.csv")
pairs = {(r["question_id"], r["child_occurrence_id"]) for r in slots}
future = [r for r in slots if r["timestamp_chronology"] == "FUTURE"]
assert (len(slots), len(pairs)) == (2000, 1014)
assert len({(r["question_id"], r["child_occurrence_id"])
            for r in future}) == 33
assert len({r["question_id"] for r in future}) == 14
assert set(labels) <= pairs

covered = 0
for system in ("E1", "E2", "E3", "E4"):
    directory = root / f"results/week4_v2/week4_v2_{system.lower()}_full_002"
    receipt = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    with (directory / "answers.jsonl").open(encoding="utf-8") as f:
        answers = [json.loads(line) for line in f if line.strip()]
    assert receipt["status"] == "COMPLETE" and len(answers) == 100
    for metric in ("answer_em", "answer_f1"):
        mean = sum(a["metrics"][metric]["value"] for a in answers) / len(answers)
        assert abs(mean - summary[metric]["value"]) < 1e-12
    subset = [r for r in slots if r["system"] == system]
    counts = Counter(labels[(r["question_id"], r["child_occurrence_id"])]
                     for r in subset
                     if (r["question_id"], r["child_occurrence_id"]) in labels)
    covered += sum(counts.values())
    print(system, summary["answer_em"]["value"],
          summary["answer_f1"]["value"],
          sum(r["timestamp_chronology"] == "FUTURE" for r in subset), counts)
assert covered == 327
print("Annotated slot coverage:", covered / len(slots) * 100)
```

## 11. Conclusion and Next Research Phase

The completed v2 runs establish a reproducible artifact-based answer-scoring reference on the fixed StreamingQA development frame. E4 records the highest observed answer scores, without established statistical superiority. Mechanical chronology shows future-dated retrieval exposure, while the bounded relevance pilot supplies useful but incomplete, purposefully selected judgments. Full-dataset retrieval relevance metrics remain unavailable.

The next research phase is intended to investigate controlled freshness-poisoning attacks and their effects on retrieval, evidence selection, and answer generation. Such work would require an explicit experimental design and appropriate authorization, with relevance/key ambiguities and provenance limitations addressed. This report neither claims that phase is completed nor authorizes it.
