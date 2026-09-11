"""
Weeks 3-4 | StreamingQA snapshot generation.

Downloads the StreamingQA 'eval' subset (the subset with 3 gold answers per
question, per the dataset README -- more robust than train/valid, which have
only 1), then draws a seeded n=100 sample, mirroring the TriviaQA control
snapshot convention (save_snapshot.py: seed=42, n=100).

Source: google-deepmind/streamingqa (Liska et al., 2022, ICML).
https://github.com/google-deepmind/streamingqa

NOTE: this only samples QUESTIONS + METADATA (question, answers, question_ts,
evidence_ts, evidence_id, recent_or_past). It does NOT yet fetch the actual
WMT news-article text for evidence_id / candidate passages -- that requires
downloading WMT News Crawl archive file(s) and running the dataset's
extraction.py, which we do in a second step once we know which years this
seeded sample's evidence_ts values actually span (no reason to pull all 14
years of WMT data if the sample only touches a few of them).
"""

import gzip
import json
import random
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # src/eval -> src -> repo root
RAW_DIR = REPO_ROOT / "data" / "raw"

EVAL_URL = "https://storage.googleapis.com/dm-streamingqa/streaminqa_eval.jsonl.gz"
RAW_GZ_PATH = RAW_DIR / "streamingqa_eval.jsonl.gz"
SAMPLE_PATH = RAW_DIR / "streamingqa_control_sample.jsonl"

SEED = 42
N = 100


def download_eval_subset(url: str = EVAL_URL, out_path: Path = RAW_GZ_PATH) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url} -> {out_path}")
    urllib.request.urlretrieve(url, out_path)


def load_eval_subset(gz_path: Path = RAW_GZ_PATH) -> list[dict]:
    with gzip.open(gz_path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def save_sample(records: list[dict], seed: int = SEED, n: int = N,
                 out_path: Path = SAMPLE_PATH) -> list[dict]:
    random.seed(seed)
    sample = random.sample(records, n)
    with open(out_path, "w", encoding="utf-8") as f:
        for row in sample:
            f.write(json.dumps(row) + "\n")
    return sample


if __name__ == "__main__":
    download_eval_subset()
    records = load_eval_subset()
    sample = save_sample(records)

    # Report the evidence_ts range so step 2 (WMT archive fetch) knows
    # exactly which news-docs.<year>.en.filtered.gz files it needs.
    import datetime
    years = sorted({
        datetime.datetime.utcfromtimestamp(r["evidence_ts"]).year
        for r in sample
    })
    print(f"Sampled {len(sample)} questions.")
    print(f"evidence_ts spans years: {years}")
    print("-> pass this year list to the WMT archive fetch step.")