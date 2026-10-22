# Week-5 pilot v1 (non-nested) results - legacy, exploratory only

These files were produced by the first three-question pilot (commits up to
dc937b4). They are kept for comparison only and must NOT be combined with the
v2 (nested, source_qa_id-paired) results.

Known problems that v2 fixes:
- Payloads were paired with questions by file order; the payload `question_id`s
  were the qa_ids of raw records 0-2, not of the pilot questions.
- Poison counts were not nested: the n=1 slot was chosen by a different code
  path from n=2/n=5, so P1 was not a subset of P2.
- Run logs recorded `attack_condition: "clean"` for every attacked run, and no
  model revisions, config hash, pool hash or seed.

The manual labels in `pilot_harm_review.csv` and `pilot_djokovic_review.csv`
(adopted_poison / phrasing_only / resisted) refer to these v1 rows. They remain
acceptable development labels for the pilot (supervisor item 4) and are used as
separate metadata when checking the rule-based answer judge.
Attacked v1 logs: logs/legacy/pilot_attacks_v1_nonnested/.
v1 pools: data/processed/attack_pools/legacy/pilot_v1_nonnested/.
