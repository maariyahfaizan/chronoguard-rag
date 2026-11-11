# ChronoGuard-RAG — A17 Child Relevance Calibration

## Purpose
Evaluate child-level semantic relevance independently.
Do not inherit parent-level relevance labels.

## Labels

- RELEVANT: The child independently contains sufficient evidence
  supporting a correct answer to the question.
- NOT_RELEVANT: The child does not provide sufficient evidence
  supporting a correct answer.
- UNKNOWN: The child is ambiguous, incomplete, contradictory,
  or cannot be reliably judged.

## Reviewer instructions

1. Read the question and accepted gold answers.
2. Read only the selected child passage as evidence.
3. Decide whether that child supports a correct answer.
4. Do not infer missing evidence from its parent passage.
5. Do not assign relevance solely because the gold answer appears.
6. Keep temporal validity and source authority separate.
7. Record a short evidence-based explanation.
8. Use UNKNOWN whenever the evidence is insufficient to decide reliably.

## Independent double review

The 30 selected items must be independently annotated by
a second reviewer without seeing the first reviewer's labels.

After both reviews, compute raw agreement and Cohen's kappa.
Adjudicate disagreements and preserve both original judgments.

## Scientific restrictions

- This is a calibration pilot, not an approved full-corpus gold standard.
- No E1-E4 retrieval relevance metrics may use unreviewed UNKNOWN labels.
- Do not replace the immutable A15 package with annotation files.
- Do not infer temporal validity from publication timestamps alone.
