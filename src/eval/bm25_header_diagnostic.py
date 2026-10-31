"""Synthetic BM25 header/tokenizer diagnostics; never loads model backends."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform

from src.attacks.freshness_smoke import (
    SYNTHETIC_EXAMPLES, build_conditions, canonical_jsonl,
)

SCHEMA = "chronoguard.synthetic-bm25-header-diagnostic/v1"
HEADERS = {"neutral": "", "freshness": "Latest update:\n",
           "general_notice": "General notice:\n"}
TOKENIZERS = ("frozen_space_split", "diagnostic_whitespace_split")
PARAMETERS = {"k1": 1.5, "b": 0.75, "epsilon": 0.25, "top_k": 20}
ABS_TOL = REL_TOL = 1e-12
CONTRASTS = (("neutral", "freshness"), ("neutral", "general_notice"),
             ("general_notice", "freshness"))


def tokenize(text, name):
    if name == "frozen_space_split":
        return text.split(" ")
    if name == "diagnostic_whitespace_split":
        return text.split()
    raise ValueError(f"unknown tokenizer: {name}")


def render_conditions(example):
    """Change only rendered poison text; labels live outside original records."""
    neutral = build_conditions(example, seed=42)[1]
    records = {}
    for condition, header in HEADERS.items():
        record = copy.deepcopy(neutral)
        record["candidates"][1]["text"] = header + example.incorrect_claim
        records[condition] = record
    validate_controls(records)
    return records


def validate_controls(records):
    if set(records) != set(HEADERS):
        raise ValueError("expected exactly three header conditions")
    neutral = records["neutral"]
    if len(neutral["candidates"]) != 2:
        raise ValueError("expected correct then poison")
    for condition, header in HEADERS.items():
        normalized = copy.deepcopy(records[condition])
        text = normalized["candidates"][1]["text"]
        if not text.startswith(header):
            raise ValueError("declared header missing")
        normalized["candidates"][1]["text"] = text[len(header):]
        if normalized != neutral:
            raise ValueError("control differs beyond declared header")
    for name in TOKENIZERS:
        fresh, general = (records[c]["candidates"][1]["text"]
                          for c in ("freshness", "general_notice"))
        if (len(tokenize(fresh, name)) != len(tokenize(general, name))
                or len(tokenize(HEADERS["freshness"], name))
                != len(tokenize(HEADERS["general_notice"], name))):
            raise ValueError("header token counts differ")


def independent_components(documents, query_tokens):
    """Scalar BM25 formula computed independently of library internals/scores.

    Repeated query tokens contribute repeatedly, as in rank-bm25 0.2.2.
    Negative raw IDFs use epsilon * mean(raw IDF), even when negative.
    """
    n = len(documents)
    counts = [Counter(tokens) for tokens in documents]
    lengths = list(map(len, documents))
    avgdl = sum(lengths) / n
    df = Counter(term for count in counts for term in count)
    raw = {term: math.log(n - freq + 0.5) - math.log(freq + 0.5)
           for term, freq in sorted(df.items())}
    average_idf = sum(raw.values()) / len(raw)
    floor = PARAMETERS["epsilon"] * average_idf
    effective = {term: floor if value < 0 else value for term, value in raw.items()}
    traces = []
    for count, length in zip(counts, lengths):
        terms = []
        for position, token in enumerate(query_tokens):
            tf = count[token]
            normalizer = PARAMETERS["k1"] * (
                1 - PARAMETERS["b"] + PARAMETERS["b"] * length / avgdl)
            contribution = effective.get(token, 0.0) * (
                tf * (PARAMETERS["k1"] + 1) / (tf + normalizer))
            terms.append({"query_position": position, "token": token, "tf": tf,
                          "effective_idf": effective.get(token, 0.0),
                          "contribution": contribution})
        traces.append(terms)
    return {"document_lengths": lengths, "average_document_length": avgdl,
            "document_count": n, "vocabulary_size": len(df),
            "document_frequencies": dict(sorted(df.items())), "raw_idf": raw,
            "average_idf": average_idf, "negative_idf_adjustment": floor,
            "effective_idf": effective}, traces


def _close(left, right):
    if not (math.isfinite(left) and math.isfinite(right)
            and math.isclose(left, right, rel_tol=REL_TOL, abs_tol=ABS_TOL)):
        raise ValueError(f"independent/library numerical mismatch: {left!r} vs {right!r}")


def measure(example, condition, record, tokenizer):
    from rank_bm25 import BM25Okapi
    documents = [tokenize(c["text"], tokenizer) for c in record["candidates"]]
    query_tokens = tokenize(record["query"], tokenizer)
    statistics, traces = independent_components(documents, query_tokens)
    index = BM25Okapi(documents, k1=1.5, b=0.75, epsilon=0.25)
    scores = [float(s) for s in index.get_scores(query_tokens)]
    _close(statistics["average_idf"], index.average_idf)
    for token in index.idf:
        _close(statistics["effective_idf"][token], index.idf[token])
    if tokenizer == "frozen_space_split":
        from src.retrieval.bm25 import retrieve_best
        outputs = retrieve_best(record["query"], [c["text"] for c in record["candidates"]], top_k=20)
        original_source = "existing src.retrieval.bm25.retrieve_best"
    else:
        order = sorted(range(2), key=lambda i: scores[i], reverse=True)
        outputs = [(i, record["candidates"][i]["text"], scores[i]) for i in order]
        original_source = "diagnostic split() BM25Okapi with stable descending score order"
    resolved = sorted(range(2), key=lambda i: (-scores[i], i))
    passages = []
    for rank, (i, text, score) in enumerate(outputs, 1):
        _close(float(score), scores[i])
        if text != record["candidates"][i]["text"]:
            raise ValueError("retriever changed passage text")
        total = sum(t["contribution"] for t in traces[i])
        _close(total, scores[i])
        passages.append({"candidate_index": i, "doc_id": record["candidates"][i]["doc_id"],
                         "role": "correct" if i == 0 else "poison", "text": text,
                         "score": float(score), "original_rank": rank,
                         "resolved_rank": resolved.index(i) + 1,
                         "score_tied": scores.count(scores[i]) > 1,
                         "query_token_contributions": traces[i],
                         "independent_score": total, "score_residual": total - scores[i]})
    return {"kind": "measurement", "scope": "synthetic_diagnostic", "source_qa_id": example.source_qa_id,
            "condition": condition, "header": HEADERS[condition], "tokenizer": tokenizer,
            "input": copy.deepcopy(record), "query_tokens": query_tokens,
            "document_tokens": documents, "statistics": statistics,
            "library_average_idf": float(index.average_idf),
            "library_effective_idf": {k: float(v) for k, v in sorted(index.idf.items())},
            "original_order_source": original_source,
            "original_outputs": passages, "deterministic_order": resolved,
            "poison_minus_correct_margin": scores[1] - scores[0]}


def comparison(left, right):
    a = {r["candidate_index"]: r for r in left["original_outputs"]}
    b = {r["candidate_index"]: r for r in right["original_outputs"]}
    return {"kind": "comparison", "scope": "synthetic_diagnostic",
            "source_qa_id": left["source_qa_id"], "tokenizer": left["tokenizer"],
            "reference": left["condition"], "target": right["condition"],
            "passage_deltas": [{"doc_id": a[i]["doc_id"],
                "score_delta": b[i]["score"] - a[i]["score"],
                "original_rank_delta": b[i]["original_rank"] - a[i]["original_rank"],
                "resolved_rank_delta": b[i]["resolved_rank"] - a[i]["resolved_rank"]} for i in (0, 1)],
            "margin_delta": right["poison_minus_correct_margin"] - left["poison_minus_correct_margin"]}


def lexical_audit(records):
    audit = {}
    for tokenizer in TOKENIZERS:
        fresh, general = [tokenize(records[c]["candidates"][1]["text"], tokenizer)
                          for c in ("freshness", "general_notice")]
        query = set(tokenize(records["neutral"]["query"], tokenizer))
        audit[tokenizer] = {"freshness_poison_length": len(fresh), "general_poison_length": len(general),
                            "freshness_only_tokens": sorted(set(fresh) - set(general)),
                            "general_only_tokens": sorted(set(general) - set(fresh)),
                            "freshness_query_overlap": sorted(set(fresh) & query),
                            "general_query_overlap": sorted(set(general) & query)}
    return audit


def require_dependency():
    version = importlib.metadata.version("rank-bm25")
    if version != "0.2.2":
        raise ValueError(f"rank-bm25==0.2.2 required, found {version}")
    return version


def run_diagnostic():
    version = require_dependency()
    root = Path(__file__).resolve().parents[2]
    sources = ("src/attacks/freshness_smoke.py", "src/retrieval/bm25.py",
               "src/eval/bm25_header_diagnostic.py")
    rows = [{"kind": "manifest", "schema": SCHEMA, "scope": "synthetic_diagnostics_not_attack_success",
             "python": platform.python_version(), "rank_bm25": version,
             "numpy": importlib.metadata.version("numpy"), "parameters": PARAMETERS,
             "numerical_tolerance": {"absolute": ABS_TOL, "relative": REL_TOL},
             "source_sha256": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in sources},
             "semantic_difference": "Latest update asserts recency; General notice does not. Equal token counts are structural controls only.",
             "tie_policy": "exact scores; deterministic rank uses score descending then candidate index",
             "delta_definition": "target minus reference; negative rank delta means improvement",
             "lexical_audits": {e.source_qa_id: lexical_audit(render_conditions(e)) for e in SYNTHETIC_EXAMPLES}}]
    for example in SYNTHETIC_EXAMPLES:
        records = render_conditions(example)
        saved = copy.deepcopy(records)
        for tokenizer in TOKENIZERS:
            measured = {condition: measure(example, condition, record, tokenizer)
                        for condition, record in records.items()}
            rows.extend(measured.values())
            rows.extend(comparison(measured[a], measured[b]) for a, b in CONTRASTS)
        if records != saved:
            raise ValueError("diagnostic mutated input records")
    validate_results(rows)
    return rows


def validate_results(rows):
    counts = Counter(r["kind"] for r in rows)
    if counts != {"manifest": 1, "measurement": 12, "comparison": 12}:
        raise ValueError(f"unexpected record counts: {counts}")
    expected = {(e.source_qa_id, t, c) for e in SYNTHETIC_EXAMPLES for t in TOKENIZERS for c in HEADERS}
    measured = [r for r in rows if r["kind"] == "measurement"]
    if {(r["source_qa_id"], r["tokenizer"], r["condition"]) for r in measured} != expected:
        raise ValueError("measurement identities do not match design")
    for example in SYNTHETIC_EXAMPLES:
        for tokenizer in TOKENIZERS:
            group = {r["condition"]: r for r in measured
                     if r["source_qa_id"] == example.source_qa_id and r["tokenizer"] == tokenizer}
            validate_controls({c: r["input"] for c, r in group.items()})
            if {c: r["input"] for c, r in group.items()} != render_conditions(example):
                raise ValueError("inputs differ from synthetic specifications")
            for condition, row in group.items():
                outputs = row["original_outputs"]
                if len(outputs) != 2 or {p["candidate_index"] for p in outputs} != {0, 1}:
                    raise ValueError("missing passage measurements")
                if sorted(p["original_rank"] for p in outputs) != [1, 2] or sorted(p["resolved_rank"] for p in outputs) != [1, 2]:
                    raise ValueError("invalid ranks")
                for p in outputs:
                    candidate = row["input"]["candidates"][p["candidate_index"]]
                    if p["doc_id"] != candidate["doc_id"] or p["text"] != candidate["text"]:
                        raise ValueError("passage identity mismatch")
                    _close(sum(x["contribution"] for x in p["query_token_contributions"]), p["score"])
            for a, b in CONTRASTS:
                found = [r for r in rows if r["kind"] == "comparison" and r["source_qa_id"] == example.source_qa_id
                         and r["tokenizer"] == tokenizer and r["reference"] == a and r["target"] == b]
                if len(found) != 1 or found[0] != comparison(group[a], group[b]):
                    raise ValueError("comparison identity or arithmetic mismatch")


def inventory(directory):
    directory = Path(directory)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("prior results must be an existing non-symlink directory")
    paths = sorted(directory.rglob("*"))
    if any(p.is_symlink() for p in paths):
        raise ValueError("prior results must not contain symlinks")
    hashes = {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in paths if p.is_file()}
    if not hashes:
        raise ValueError("prior results directory is empty")
    return hashes


def execute(prior_dir, out_dir):
    prior, out = Path(prior_dir).resolve(), Path(out_dir).resolve()
    if prior == out or prior in out.parents or out in prior.parents or out.exists():
        raise ValueError("output must be new and non-overlapping with prior results")
    before = inventory(prior_dir)
    first, second = run_diagnostic(), run_diagnostic()
    encoded = canonical_jsonl(first).encode("utf-8")
    if encoded != canonical_jsonl(second).encode("utf-8"):
        raise ValueError("repeat serialization mismatch")
    after = inventory(prior_dir)
    if before != after:
        raise ValueError("prior results changed; no outputs written")
    validate_results([json.loads(line) for line in encoded.splitlines()])
    summary = {"scope": "synthetic_diagnostic", "validation": "passed", "repeat_identical": True,
               "measurement_count": 12, "passage_count": 24, "comparison_count": 12,
               "prior_sha256_before": before, "prior_sha256_after": after}
    out.mkdir(parents=True, exist_ok=False)
    (out / "results.jsonl").write_bytes(encoded)
    (out / "validation.json").write_bytes(canonical_jsonl([summary]).encode("utf-8"))
    hashes = {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
              for name in ("results.jsonl", "validation.json")}
    (out / "sha256.json").write_bytes(canonical_jsonl([hashes]).encode("utf-8"))
    if inventory(prior_dir) != before:
        raise ValueError("prior results changed during output writing")
    return summary, hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--repeat-check", action="store_true", help="repeat check is always enforced")
    args = parser.parse_args()
    summary, hashes = execute(args.prior_dir, args.out_dir)
    print(canonical_jsonl([summary, hashes]), end="")


if __name__ == "__main__":
    main()
