#!/usr/bin/env python3
"""Second FreshEval judge (Gate B item 9).

Reuses the SAME prompt builder, response parser and generation mechanics as the Mistral judge
(src/eval/freshqa_judge.py), so the only difference between the two judges is the model.
It never modifies the frozen run logs; verdicts go to separate files.

Backends:
    hf   (default, FREE)  an open model run locally on a Kaggle GPU, 4-bit.
                          Default model: Qwen/Qwen2.5-14B-Instruct (different family from Mistral).
    api  (paid)           the Anthropic API; needs ANTHROPIC_API_KEY.

Usage (from the repo root; the hf backend needs a GPU, so run it on Kaggle):
    python scripts/judge2_run.py --dry-run          # plumbing test, no model, no cost
    python scripts/judge2_run.py                    # the 112 validation items -> key.csv
    python scripts/judge_validation_agreement.py
    python scripts/judge2_run.py --all              # optional: every verdict in all 4 logs
    python scripts/judge2_run.py --model <hf-repo-id>   # use another open model

Outputs (results/judge_validation/):
    judge2_raw.jsonl   one line per validation item (resumable; delete it to redo)
    key.csv            judge2_label / judge2_rationale filled in (key.csv.bak saved once)
    judge2_all.jsonl   only with --all
Each record stores the model name and, for hf, the exact model commit hash.
"""
import argparse
import csv
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------- EDIT THESE ----------------------------------
HF_MODEL_DEFAULT = "Qwen/Qwen2.5-14B-Instruct"
API_MODEL_DEFAULT = "claude-sonnet-5-5"     # only used with --backend api
MAX_TOKENS = 300       # Mistral's 80-token cap truncated some rationales; do not repeat that
JUDGE_FILE = "src/eval/freshqa_judge.py"
CONDITION = "clean"
D = Path("results/judge_validation")
LOGS = {  # same file -> system mapping as the sampling script
    "E1_BM25": "logs/freshqa_baseline_run.jsonl",
    "E2_Dense": "logs/freshqa_dense_run.jsonl",
    "E3_Hybrid": "logs/freshqa_hybrid_run.jsonl",
    "E4_Hybrid+Reranker": "logs/freshqa_hybrid_reranker.jsonl",
}
# --------------------------------------------------------------------------

API_URL = "https://api.anthropic.com/v1/messages"
_use_temperature = True


def load_judge_module():
    spec = importlib.util.spec_from_file_location("freshqa_judge", JUDGE_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ----------------------------- backends -----------------------------------
def make_hf_judge(model_name, judge_mod, device_map_mode="single"):
    """Load an open model in 4-bit and reuse the repo's own _call_judge_model()."""
    import torch
    try:
        import bitsandbytes  # noqa: F401
    except ImportError:
        sys.exit('bitsandbytes is not installed in this session. Run: pip install -U "bitsandbytes>=0.46.1"')
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    if not torch.cuda.is_available():
        sys.exit("No GPU found. Run the hf backend on Kaggle with the GPU accelerator turned on.")
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=torch.float16)   # T4 has no bfloat16
    print(f"loading {model_name} in 4-bit (the first run downloads the weights)...")
    tok = AutoTokenizer.from_pretrained(model_name)
    # "single" keeps the whole 4-bit model on GPU 0 (about 10 GB for a 14B model). "auto" splits it
    # across GPUs, which ran out of memory on Kaggle's 2 x T4. fp16 is explicit because a T4 has no
    # bfloat16 and the non-quantized layers would otherwise load in the checkpoint's bf16.
    device_map = "auto" if device_map_mode == "auto" else {"": 0}
    model = AutoModelForCausalLM.from_pretrained(model_name, quantization_config=bnb,
                                                 device_map=device_map, dtype=torch.float16)
    model.eval()
    for i in range(torch.cuda.device_count()):
        print(f"GPU {i}: {torch.cuda.memory_allocated(i) / 1e9:.1f} GB allocated after loading")
    judge_mod.JUDGE_MAX_NEW_TOKENS = MAX_TOKENS     # read at call time inside _call_judge_model
    revision = getattr(model.config, "_commit_hash", None)
    print("model revision:", revision)
    return (lambda prompt: judge_mod._call_judge_model(prompt, (model, tok))), revision


def call_api(prompt, api_key, model_name):
    global _use_temperature
    for attempt in range(6):
        payload = {"model": model_name, "max_tokens": MAX_TOKENS,
                   "messages": [{"role": "user", "content": prompt}]}
        if _use_temperature:
            payload["temperature"] = 0
        req = urllib.request.Request(
            API_URL, data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return "".join(b.get("text", "") for b in data.get("content", [])
                           if b.get("type") == "text")
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")[:300]
            if e.code == 400 and "temperature" in msg.lower() and _use_temperature:
                _use_temperature = False
                continue
            if e.code in (429, 500, 502, 503, 529) and attempt < 5:
                time.sleep(2 ** attempt * 2)
                continue
            raise RuntimeError(f"API error {e.code}: {msg}")
        except (urllib.error.URLError, TimeoutError):
            if attempt < 5:
                time.sleep(2 ** attempt * 2)
                continue
            raise
    raise RuntimeError("API call failed after retries")


# ----------------------------- data helpers -------------------------------
def load_logs():
    recs = {}
    for system, path in LOGS.items():
        if not Path(path).exists():
            sys.exit(f"Missing log file: {path}")
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("attack_condition", CONDITION) != CONDITION:
                continue
            recs[(system, str(r["query_id"]))] = r
    return recs


def load_store(path):
    store = {}
    if path.exists():
        for line in open(path, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                store[(r["system"], str(r["query_id"]))] = r
    return store


def run(items, logs, store, store_path, judge_mod, judge_fn, model_label, revision):
    todo = [k for k in items if k not in store]
    print(f"{len(items)} items, {len(items) - len(todo)} already done, {len(todo)} to run")
    failed = 0
    with open(store_path, "a", encoding="utf-8") as out:
        for n, (system, qid) in enumerate(todo, 1):
            r = logs[(system, qid)]
            prompt = judge_mod._build_judge_prompt(
                question=r["query"], model_answer=r["generated_answer"],
                gold_answer=r["gold_answer"], gold_aliases=r.get("gold_aliases", []),
                false_premise=r.get("false_premise"))
            try:
                raw = judge_fn(prompt)
            except Exception as e:   # recorded as None (unknown), never as False
                raw = f"[call failed: {e}]"
            parsed = judge_mod._parse_judge_response(raw)
            if parsed["correct"] is None:
                failed += 1
            entry = {"system": system, "query_id": qid, "correct": parsed["correct"],
                     "rationale": parsed["rationale"], "model": model_label,
                     "revision": revision, "raw": raw}
            out.write(json.dumps(entry, ensure_ascii=False) + "\n")
            out.flush()
            store[(system, qid)] = entry
            if n % 10 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)} done ({failed} unparsed/failed so far)")
    return failed


def write_key(store):
    key_path = D / "key.csv"
    bak = D / "key.csv.bak"
    if not bak.exists():
        bak.write_bytes(key_path.read_bytes())
    rows = list(csv.DictReader(open(key_path, encoding="utf-8-sig")))
    fields = list(rows[0].keys())
    for extra in ("judge2_label", "judge2_rationale"):
        if extra not in fields:
            fields.append(extra)
    for row in rows:
        e = store.get((row["system"], str(row["query_id"])))
        if e and e["correct"] is not None:
            row["judge2_label"] = "1" if e["correct"] else "0"
            row["judge2_rationale"] = e["rationale"]
        else:
            row["judge2_label"] = ""
            row["judge2_rationale"] = e["rationale"] if e else ""
    with open(key_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    filled = sum(1 for r in rows if r["judge2_label"] != "")
    print(f"key.csv updated: {filled}/{len(rows)} items have a judge2_label (backup: {bak.name})")


def summarize_all(logs, store):
    print("\naccuracy over all clean items (undefined verdicts excluded):")
    print(f"  {'system':22s} {'n':>4s}  {'judge1(Mistral)':>16s}  {'judge2':>8s}")
    for system in LOGS:
        j1 = [bool(r["fresheval_correct"]) for (s, _), r in logs.items()
              if s == system and r.get("fresheval_correct") is not None]
        j2 = [e["correct"] for (s, _), e in store.items() if s == system and e["correct"] is not None]
        a1 = sum(j1) / len(j1) if j1 else float("nan")
        a2 = sum(j2) / len(j2) if j2 else float("nan")
        print(f"  {system:22s} {len(j2):4d}  {a1:16.4f}  {a2:8.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["hf", "api"], default="hf")
    ap.add_argument("--model", default=None, help="model id (hf repo id, or API model name)")
    ap.add_argument("--all", action="store_true", help="judge every item in all four logs")
    ap.add_argument("--dry-run", action="store_true", help="no model, no API; tests the plumbing")
    ap.add_argument("--device-map", choices=["single", "auto"], default="single",
                    help="hf backend: single = whole model on GPU 0 (default), auto = split across GPUs")
    args = ap.parse_args()

    default_model = HF_MODEL_DEFAULT if args.backend == "hf" else API_MODEL_DEFAULT
    model_name = args.model or os.environ.get("JUDGE2_MODEL") or default_model

    judge_mod = load_judge_module()
    logs = load_logs()

    if args.dry_run:
        judge_fn, revision, label = (lambda p: '{"correct": true, "rationale": "dry run"}'), None, "dry-run"
        print("DRY RUN: verdicts are fake, and no files will be written")
    elif args.backend == "api":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            sys.exit('ANTHROPIC_API_KEY is not set. PowerShell: $env:ANTHROPIC_API_KEY = "<your key>"')
        judge_fn, revision, label = (lambda p: call_api(p, api_key, model_name)), None, model_name
    else:
        os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")  # before torch starts CUDA
        judge_fn, revision = make_hf_judge(model_name, judge_mod, args.device_map)
        label = model_name

    dry = args.dry_run

    def open_store(path):
        """Dry runs touch no files. Real runs reuse only verdicts made by the SAME model."""
        if dry:
            return {}, Path(os.devnull)
        all_entries = load_store(path)
        store = {k: v for k, v in all_entries.items() if v.get("model") == label}
        if len(store) != len(all_entries):
            print(f"note: ignoring {len(all_entries) - len(store)} stored verdicts made by a different model")
        return store, path

    if args.all:
        store, store_path = open_store(D / "judge2_all.jsonl")
        run(sorted(logs.keys()), logs, store, store_path, judge_mod, judge_fn, label, revision)
        summarize_all(logs, store)
    else:
        key_rows = list(csv.DictReader(open(D / "key.csv", encoding="utf-8-sig")))
        items = [(r["system"], str(r["query_id"])) for r in key_rows]
        store, store_path = open_store(D / "judge2_raw.jsonl")
        run(items, logs, store, store_path, judge_mod, judge_fn, label, revision)
        if dry:
            print("dry run: key.csv and the result files were NOT touched")
        else:
            write_key(store)
            print("Next: python scripts/judge_validation_agreement.py")


if __name__ == "__main__":
    main()