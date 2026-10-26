
Week 4 Post-Freeze Validation (W4-F1)
Status: PASS — executed on 2026-10-23 (UTC). All recorded E2–E4 configuration, row-logging, and retrieval-count checks passed.

These E2, E3 and E4 config-driven smoke tests are post-freeze validation. They do not change the frozen Week-4 baseline:

the week4-frozen tag (annotated tag f26a389 → commit d995f83) is not moved or recreated;
no frozen config, log or result is edited;
no Week-4 baseline rerun is performed.
What was run
The post-freeze validation using scripts/smoke_test_e2_e4_post_freeze.py (Kaggle GPU) did the following:

Ran E2, E3 and E4 on the first 5 queries of the frozen pool data/processed/streamingqa_control_pools_chunked.jsonl.
Called each driver without retrieval parameters, so they came from configs/streamingqa_eval_config.yaml.
Reused models preloaded in the Kaggle notebook. Configured revisions were recorded in the report, but the validator did not independently verify the loaded revisions.
Wrote outputs to logs/week4_post_freeze_smoke/ and results/week4_post_freeze_smoke.json, without modifying frozen Week-4 artifacts.
Pass criteria (per system):

every query is logged;
logged top_k / candidate_top_k / fused_top_k / final_top_k / rrf_k / reranker equal the YAML wherever applicable;
each query retrieves exactly the configured number of passages.
Reported, not pass criteria: whether retrieved indices and answers equal the frozen Week-4 logs for the same queries. The frozen runs did not record model revisions, so a difference would not itself constitute a smoke-test failure.

Results
Execution timestamp (UTC): 2026-10-23T05:26:15.853325+00:00
Overall result: PASS
Queries tested: 5 per system, using the first five queries of the frozen StreamingQA chunked pool.

System	Pass	Same retrieval as frozen (of 5)	Same answer as frozen (of 5)
E2	PASS	5/5	5/5
E3	PASS	5/5	5/5
E4	PASS	5/5	5/5
All recorded configuration, row-logging and retrieval-count checks passed for E2, E3 and E4.

Execution provenance
Run commit: 78d3181526b0b5eda6008dcbb6850aedbf63021a
Working tree: dirty: true
Result file: results/week4_post_freeze_smoke.json
Frozen pool SHA-256: b4eede5c1ed4b06808fe44754cc04ee5036d3a572088de61dd6dff1f77174ddd
Five-query subset SHA-256: 3a878db309def1b83c730bcef781a81a48b98da2619b96bca544cfdffd734891
E2 log SHA-256: 8d254de193ecf2f2f8297b55f79988d1758057252be234fcd97b5ca5c5c7384e
E3 log SHA-256: 9e57323f9ab194d9aa50638a28ba3440869a6f1235231b8ee801c151ad4512d0
E4 log SHA-256: 9cb3552cf0f84a8a76bba5e3ae881f5043fd93409b23441f5048bf1062656f47
The SHA-256 of the result JSON itself is not recorded here; it can be calculated separately if needed.

Limitations
The validator reused notebook-preloaded model objects. Although configured model revisions were recorded, their actual loaded revisions were not independently verified.
Frozen Week-4 runs did not record model revisions, so matching retrieval and answers do not establish identical model environments.
The execution working tree was dirty. The report does not identify the modified or untracked files.
The test covers five queries per system. It validates the specified smoke-test checks, not statistical reproducibility or general performance.
The frozen Week-4 baseline, its results, logs, configurations and week4-frozen tag remain unchanged.
Conclusion: W4-F1 is complete. The post-freeze smoke test passed its defined criteria, and all reported retrieval and answer comparisons matched the frozen outputs.

n=5⋮⋮⋮⋮⋮⋮⋮⋮