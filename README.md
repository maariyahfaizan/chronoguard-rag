# ChronoGuard-RAG

Investigating temporal/freshness vulnerabilities in Retrieval-Augmented
Generation (RAG). This repo currently implements the clean-baseline stage
(E1-E4): four retrieval architectures evaluated on TriviaQA prior to the
introduction of temporal attacks and the ChronoGuard defense in later phases.

## Setup

```bash
pip install -r requirements.txt
```

Requires a CUDA-capable GPU for 4-bit generation with Mistral-7B-Instruct-v0.2
(developed and tested on Kaggle T4 sessions).

## Reproducing the clean baseline (E1-E4)

1. Generate the fixed evaluation sample (seed=42, n=100):
```bash
   python src/eval/save_snapshot.py
```
2. Preprocess into the clean run format:
```bash
   python src/eval/preprocess.py
```
3. Run each experiment (each writes its own log to `logs/`):
```bash
   python scripts/run_baseline.py           # E1: BM25
   python scripts/run_dense.py              # E2: Contriever
   python scripts/run_hybrid.py             # E3: BM25 + Contriever + RRF
   python scripts/run_hybrid_reranker.py    # E4: E3 + BGE reranker
```

All four scripts share the same generator (Mistral-7B-Instruct-v0.2, 4-bit,
greedy decoding), the same evaluation logic (`src/eval/evaluator.py`), and
the same fixed 100-question sample, so retrieval architecture is the only
variable that differs between them.

## Repo structure

src/
retrieval/ BM25, dense (Contriever), RRF hybrid fusion, cross-encoder reranking
generation/ Prompt construction + Mistral generation
eval/ Metrics (EM/F1/Recall@k/nDCG@k), shared evaluator, data prep
scripts/ One entry point per experiment (E1-E4)
configs/ Experiment configuration (baseline_config.yaml)
data/ raw/ (sampled dataset) and processed/ (cleaned run input)
logs/ Per-query JSONL logs, one file per experiment
tests/ Unit tests for retrieval and evaluation correctness


## Known dataset property: Recall@5/nDCG@5 saturation on TriviaQA

Recall@5 and nDCG@5 come out identical across all four systems despite
materially different retrieved passages. This is an expected property of
TriviaQA's `rc` configuration, not a bug -- see Section 4 of the project
report for the full explanation and supporting literature. StreamingQA
(next phase) does not share this construction and is expected to make these
metrics discriminative.

## Status

Clean baseline (E1-E4) complete on TriviaQA. Next phase: StreamingQA.