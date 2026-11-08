"""Six-case P0-S3B forensic text audit; never relabels or executes backends."""
import argparse
from collections import Counter
import difflib
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.eval.metrics import normalize_answer

CASES = {9: 4, 25: 14, 67: 17, 73: 9, 94: 4, 99: 11}
OUT = ROOT / "audits/p0_s3b_v1"
P3 = "audits/p0_s3_v1"
NEGATION_WORDS = {"no", "not", "never", "neither", "nor", "without", "cannot",
                  "cant", "didnt", "wasnt", "isnt", "dont", "doesnt", "wont"}
NOTES = {
    9: "Closing quotation-like marks are removed. Attribution/quotation boundaries may be affected; do not assume harmlessness.",
    25: "Trademark markers are removed. Brand/legal notation changes; no claim of semantic equivalence.",
    67: "A half-fraction in an acreage quantity is removed. Numeric meaning can change.",
    73: "A half-fraction in a quoted share price is removed. Numeric meaning can change.",
    94: "A half-fraction in a route distance is removed. Quantitative meaning is lost.",
    99: "A replacement character in a photo-credit/caption is removed. The parent already contains U+FFFD; whether this was introduced by earlier decoding or was present upstream is unknown. The original character is not established. Literal answer matches survive in both children, but semantic/provenance equivalence is not established.",
}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode() + b"\n"


def nonwhite(text):
    offsets = [i for i, char in enumerate(text) if not char.isspace()]
    return "".join(text[i] for i in offsets), offsets


def stitch(texts):
    """Diagnostic view only: require a UNIQUE exact adjacent overlap, not a guess.

    All origin coordinates survive; no parent-dependent deletion allowance is used.
    This view is never passed to the labeler or used to unblock a question.
    """
    require(bool(texts), "no children")
    joined, offsets = nonwhite(texts[0])
    require(bool(joined), "empty diagnostic child")
    origins = [[(0, i)] for i in offsets]
    overlaps = []
    for child_index, text in enumerate(texts[1:], 1):
        part, indices = nonwhite(text)
        possible = [n for n in range(1, min(len(joined), len(part)) + 1)
                    if joined[-n:] == part[:n]]
        require(len(possible) == 1, "ambiguous or missing diagnostic overlap")
        n = possible[0]
        for j in range(n):
            origins[len(joined) - n + j].append((child_index, indices[j]))
        origins.extend([[(child_index, i)] for i in indices[n:]])
        joined += part[n:]
        overlaps.append({"left_child_index": child_index - 1, "right_child_index": child_index,
                         "exact_nonwhitespace_overlap_candidates": possible,
                         "selected_overlap": n})
    return joined, origins, overlaps


def text_differences(parent, child_texts):
    parent_view, offsets = nonwhite(parent)
    child_view, origins, overlaps = stitch(child_texts)
    edits = []
    matcher = difflib.SequenceMatcher(a=parent_view, b=child_view, autojunk=False)
    for op, start, end, cstart, cend in matcher.get_opcodes():
        if op == "equal":
            continue
        raw_start = offsets[start] if start < len(offsets) else len(parent)
        raw_end = offsets[end - 1] + 1 if end > start else raw_start
        target = origins[cstart] if cstart < len(origins) else [(i, pos + 1) for i, pos in origins[-1]]
        edits.append({"operation": op, "parent_nonwhitespace_span": [start, end],
            "child_diagnostic_nonwhitespace_span": [cstart, cend],
            "parent_raw_character_span": [raw_start, raw_end],
            "parent_utf8_byte_span": [len(parent[:raw_start].encode()), len(parent[:raw_end].encode())],
            "removed_or_replaced": parent_view[start:end], "replacement": child_view[cstart:cend],
            "unicode_characters": [{"character": char, "codepoint": f"U+{ord(char):04X}",
                "name": unicodedata.name(char, "UNNAMED"), "category": unicodedata.category(char),
                "NFKC_description_only_not_an_exception": unicodedata.normalize("NFKC", char)}
                for char in parent_view[start:end]],
            "parent_context": {"start": max(0, raw_start - 55),
                "text": parent[max(0, raw_start - 55):raw_end + 55]},
            "child_contexts_at_edit_boundary": [{"child_index": i, "raw_character_offset": pos,
                "context_start": max(0, pos - 55), "text": child_texts[i][max(0, pos - 55):pos + 55]}
                for i, pos in target]})
    return {"edits": edits, "overlaps": overlaps,
            "whitespace_ignored_for_alignment_only": True,
            "whitespace_only_difference": parent_view == child_view and parent != child_texts[0],
            "parent_whitespace_characters": sum(c.isspace() for c in parent),
            "child_whitespace_characters": [sum(c.isspace() for c in text) for text in child_texts],
            "diagnostic_view_sha256": sha(child_view.encode()),
            "is_equivalence_proof": False}


def literal_probe(text, answers):
    tokens = set(normalize_answer(text).split())
    return [i for i, answer in enumerate(answers)
            if (gold := set(normalize_answer(answer).split())) and gold <= tokens]


def tokenizer_evidence():
    roots = {Path.home() / ".cache/huggingface/hub", ROOT / ".cache/huggingface/hub"}
    for key in ("HF_HUB_CACHE", "TRANSFORMERS_CACHE"):
        if os.environ.get(key):
            roots.add(Path(os.environ[key]))
    if os.environ.get("HF_HOME"):
        roots.add(Path(os.environ["HF_HOME"]) / "hub")
    caches = []
    for root in sorted(roots, key=str):
        model = root / "models--BAAI--bge-reranker-base"
        files = {str(p.relative_to(model)): sha(p.read_bytes()) for p in model.rglob("*")
                 if p.is_file() and p.name in {"tokenizer.json", "tokenizer_config.json",
                    "special_tokens_map.json", "sentencepiece.bpe.model", "tokenizer.model"}}
        caches.append({"model_cache_path": str(model), "exists": model.exists(),
                       "tokenizer_configuration_files": files})
    runtime = {}
    for name in ("transformers", "tokenizers", "sentencepiece", "torch"):
        runtime[name] = {"importable": importlib.util.find_spec(name) is not None}
        try:
            runtime[name]["installed_version"] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            runtime[name]["installed_version"] = "UNAVAILABLE"
    return {"configured_name": "BAAI/bge-reranker-base", "historical_revision": "UNRECORDED",
        "historical_call": "AutoTokenizer.from_pretrained(CHUNK_TOKENIZER_NAME); no revision argument",
        "encode": "add_special_tokens=False", "decode": "skip_special_tokens=True",
        "current_week5_pin_not_historical_proof": "2cfc18c9415c912f9d8155881c133215df768a70",
        "runtime": runtime, "checked_local_caches": caches,
        "original_runtime_replay": "UNAVAILABLE_NOT_PERFORMED",
        "tokenizer_causation": "UNVERIFIED",
        "interpretation": "Encode/decode is a plausible transformation boundary in the inspected producer, but neither original token IDs, exact tokenizer configuration/revision nor runtime are available to establish why these characters disappeared. No special-token or normalizer explanation is asserted as fact."}


def build_artifacts():
    original = ROOT / P3
    require(sha((original / "sha256.json").read_bytes()) ==
            "76b323a168faf9f73b1d61a49302216d2fb52e93136bdb766271e8a90c7a4653", "P0-S3 seal changed")
    for path, expected in json.loads((original / "sha256.json").read_text()).items():
        require(sha((original / path).read_bytes()) == expected, "P0-S3 child hash changed")
    inputs = json.loads((original / "source_inventory.json").read_text())["files"]
    for path, expected in inputs.items():
        require(sha((ROOT / path).read_bytes()) == expected, "P0-S3 source hash changed")
    cases = []
    with (original / "reconciliation.jsonl").open(encoding="utf-8") as stream:
        for i, line in enumerate(stream):
            if i not in CASES:
                continue
            row = json.loads(line)
            require(row["query_id"] == i and row["proposed_labeling"] is None, "blocked state drift")
            proof = next(p for p in row["grouping_proofs"] if p["status"] == "BLOCKED")
            require(proof["parent_candidate_slot"] == CASES[i], "parent slot drift")
            parent = row["historical_parent_record"]["candidates"][CASES[i]]
            children = [row["historical_chunked_record"]["candidates"][j] for j in proof["child_slots"]]
            require(all(c["parent_doc_id"] == parent["doc_id"] and c["timestamp"] == parent["timestamp"]
                        for c in children), "lineage/metadata drift")
            differences = text_differences(parent["text"], [c["text"] for c in children])
            answers = [row["gold_answer"]] + row["gold_aliases"]
            parent_negations = sorted(set(normalize_answer(parent["text"]).split()) & NEGATION_WORDS)
            child_negations = sorted(set().union(*(set(normalize_answer(c["text"]).split())
                                                   for c in children)) & NEGATION_WORDS)
            cases.append({"query_id": i, "source_qa_id": row["source_qa_id"],
                "question": row["question"], "gold_answer": row["gold_answer"], "gold_aliases": row["gold_aliases"],
                "parent_candidate_slot": CASES[i], "child_candidate_slots": proof["child_slots"],
                "parent": parent, "children": children,
                "source_references": {"reconciliation": f"{P3}/reconciliation.jsonl:{i + 1}",
                    "parent_pool": f"data/processed/streamingqa_control_pools.jsonl:{i + 1}",
                    "child_pool": f"data/processed/streamingqa_control_pools_chunked.jsonl:{i + 1}"},
                "parent_text_sha256": sha(parent["text"].encode()),
                "child_text_sha256": [sha(c["text"].encode()) for c in children],
                "differences": differences,
                "literal_match_probe_not_proposed_labels": {"parent_answer_indices": literal_probe(parent["text"], answers),
                    "child_answer_indices": [literal_probe(c["text"], answers) for c in children]},
                "limited_negation_word_probe_not_semantic_review": {"words_checked": sorted(NEGATION_WORDS),
                    "parent_words": parent_negations, "child_union_words": child_negations,
                    "same_observed_inventory": parent_negations == child_negations},
                "timestamp_metadata_preserved": True, "identity_fields_preserved": True,
                "semantic_impact_note_provisional": NOTES[i],
                "root_cause_observed": "NONWHITESPACE_DELETION_IN_PERSISTED_CHILD_TEXT",
                "original_tokenizer_causation": "UNVERIFIED",
                "semantic_support_status": "NOT_INDEPENDENTLY_REVIEWED",
                "temporal_validity_status": "NOT_REVIEWED", "provenance_authenticity": "NOT_ESTABLISHED",
                "P0_S3_disposition": "REMAINS_BLOCKED_NO_RELABELING"})
    require([c["query_id"] for c in cases] == list(CASES), "six-case membership drift")
    tokenizer = tokenizer_evidence()
    counts = Counter(char["codepoint"] for c in cases for e in c["differences"]["edits"]
                     for char in e["unicode_characters"])
    validation = {"cases": len(cases), "observed_removed_characters": dict(sorted(counts.items())),
        "only_deletions_observed": all(e["operation"] == "delete" for c in cases for e in c["differences"]["edits"]),
        "whitespace_only_cases": sum(c["differences"]["whitespace_only_difference"] for c in cases),
        "case99_unique_nonwhitespace_child_overlap": cases[-1]["differences"]["overlaps"],
        "historical_artifacts_modified": False, "relabeling_performed": False,
        "scientific_metrics_recomputed": False, "tokenizer_explanation_verified": False,
        "status": "DIAGNOSED_TEXT_LOSS_CAUSATION_UNVERIFIED_ALL_SIX_REMAIN_BLOCKED"}
    source_files = list(inputs) + [f"{P3}/{p}" for p in json.loads((original / "sha256.json").read_text())] + [
        f"{P3}/sha256.json", "configs/model_revisions.yaml", "audits/p1_a2_v1/tokenizer_inventory.json",
        "src/eval/offline_input_audit.py", "src/eval/fetch_wmt_archives.py", "scripts/diagnose_streamingqa_coverage.py",
        "tests/test_streamingqa_coverage_diagnostics.py"]
    source_inventory = {"files": {p: sha((ROOT / p).read_bytes()) for p in sorted(set(source_files))},
        "published_head": subprocess.check_output(["git", "-c", "safe.directory=" + ROOT.as_posix(),
            "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "implementation_references": {"chunk_candidate": "src/eval/chunk_streamingqa_pools.py:144",
            "encode": "src/eval/chunk_streamingqa_pools.py:154", "decode": "src/eval/chunk_streamingqa_pools.py:159",
            "tokenizer_loading": "src/eval/chunk_streamingqa_pools.py:198", "upstream_text_bytes_replacement_possible_boundary": "src/eval/fetch_wmt_archives.py:291"},
        "publication_classification": "RESTRICTED_QUESTION_EVIDENCE_CONTEXT_NOT_APPROVED_FOR_PUBLICATION"}
    lines = ["# P0-S3B six-case coverage diagnostics", "", "RESTRICTED local question/evidence material. Not approved for publication.", "",
        "Observed differences are reproducible from sealed files. Original tokenizer causation is UNVERIFIED; no downloads or model calls were made. All six P0-S3 questions remain blocked.", "",
        "Offsets below are zero-based raw Python character spans [start,end); JSON additionally records UTF-8 byte spans and child edit-boundary contexts. Parent/child IDs and text hashes are exact, not authentication evidence.", ""]
    for case in cases:
        lines.extend([f"## Query {case['query_id']} / {case['source_qa_id']}", "",
            f"Parent occurrence {case['parent_candidate_slot']}; child slots {case['child_candidate_slots']}; historical source flag {case['parent']['is_source_document']}.",
            "Parent ID: `" + json.dumps(case["parent"]["doc_id"]) + "`",
            "Child IDs: `" + json.dumps([c["doc_id"] for c in case["children"]]) + "`",
            "Source: `" + case["source_references"]["parent_pool"] + "`; `" + case["source_references"]["child_pool"] + "`.",
            "Parent text SHA-256: `" + case["parent_text_sha256"] + "`.",
            "Child text SHA-256: `" + json.dumps(case["child_text_sha256"]) + "`.", ""])
        for edit in case["differences"]["edits"]:
            lines.extend([f"- {edit['operation']} at {edit['parent_raw_character_span']}: " +
                json.dumps(edit["unicode_characters"], ensure_ascii=True),
                "  Parent context: " + json.dumps(edit["parent_context"], ensure_ascii=True),
                "  Child boundary context: " + json.dumps(edit["child_contexts_at_edit_boundary"], ensure_ascii=True)])
        lines.extend(["", "Literal answer-index probe (not proposed labels): `" +
            json.dumps(case["literal_match_probe_not_proposed_labels"]) + "`.",
            case["semantic_impact_note_provisional"],
            "Timestamp metadata and lineage identifiers match; semantic/temporal/provenance approval is absent.", ""])
    lines.extend(["## Cause and smallest proposed non-destructive correction", "",
        "The inspected producer encodes, windows token IDs and decodes with skip_special_tokens=True. There is no explicit symbol-deletion rule. Encode/decode loss (including special/unknown-token handling or normalizer behavior) is a hypothesis, not proven with the missing original runtime/configuration. Current Week-5 revision pins do not identify the historical tokenizer. Parent U+FFFD already denotes unrecoverable original-character uncertainty; its earlier origin is unknown.", "",
        "Do not add a Unicode deletion allowlist or unblock the six records. First recover authenticated tokenizer/configuration/token-ID evidence if possible. For a future separately versioned producer, propose validated tokenizer offset mappings and raw parent-character slices, with exact source span hashes, to preserve Unicode text; validate all bytes/coverage and backend views. Do not alter the frozen decoded children or use this proposal as approval to relabel them.", "",
        "Numeric fractions can carry meaning. Quotation/trademark/replacement characters cannot be declared harmless collectively. Literal answer survival, unchanged finite negation-word probes and unchanged timestamp fields do not establish semantic equivalence, factual time validity or original-source authenticity.", "",
        "Reproduce: `python -B scripts/diagnose_streamingqa_coverage.py --check`. Creation refuses an existing output directory. Check verifies exact artifact bytes, not semantic equivalence. No scientific metrics or approvals are produced."])
    files = {"README.md": ("\n".join(lines) + "\n").encode(),
             "diagnostics.json": encoded({"cases": cases, "tokenizer_evidence": tokenizer}),
             "source_inventory.json": encoded(source_inventory), "validation.json": encoded(validation)}
    files["sha256.json"] = encoded({p: sha(data) for p, data in sorted(files.items())})
    return files, validation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files, validation = build_artifacts()
    if args.check:
        require({p.name for p in OUT.iterdir()} == set(files), "output membership changed")
        for name, data in files.items():
            require((OUT / name).read_bytes() == data, "output changed: " + name)
    else:
        OUT.mkdir(exist_ok=False)
        for name, data in files.items():
            with (OUT / name).open("xb") as stream:
                stream.write(data)
    print(json.dumps(validation, sort_keys=True))


if __name__ == "__main__":
    main()
