"""Proposed synthetic-only estimands. No real outcome ingestion or approval."""
from __future__ import annotations

import math
import random
from collections import Counter
from itertools import combinations, product

SEED = 20261104
SCHEMA = {
    "scope": "SYNTHETIC_ONLY",
    "frame_fields": {"question_id": "synthetic-stat-*", "eligibility": ["ELIGIBLE", "INELIGIBLE", "UNKNOWN", "NOT_REVIEWED"],
                     "clean": ["CORRECT", "INCORRECT", "ABSTAIN", "MISSING", "NEEDS_REVIEW"]},
    "row_fields": {"question_id": "frame reference", "family": "nonblank string", "condition": "nonblank string",
        "construction": ["SUCCEEDED", "FAILED", "UNKNOWN", "NOT_ATTEMPTED"],
        "retrieval": ["YES", "NO", "UNKNOWN", "UNAVAILABLE", "NOT_APPLICABLE"],
        "generator": ["YES", "NO", "UNKNOWN", "UNAVAILABLE", "TRUNCATED", "UNVERIFIED"],
        "outcome": ["POISON_ADOPTED", "CORRECT", "OTHER_WRONG", "ABSTAIN", "NEEDS_REVIEW", "MISSING"]},
    "row_identity": ["question_id", "family", "condition"],
    "missing_outcomes": ["NEEDS_REVIEW", "MISSING"],
    "scope_note": "ABSTAIN is a separate observed annotation, not a v2 judge label"}
RESOLVED = {"POISON_ADOPTED", "CORRECT", "OTHER_WRONG", "ABSTAIN"}
POPULATIONS = ("fixed_frame", "eligible", "clean_correct", "constructed", "retrieved", "visible", "judge_resolved")


def validate(frame, rows):
    if type(frame) is not list or type(rows) is not list:
        raise ValueError("plain lists required")
    ids = []
    for q in frame:
        if type(q) is not dict or set(q) != set(SCHEMA["frame_fields"]):
            raise ValueError("invalid frame fields")
        if not isinstance(q["question_id"], str) or not q["question_id"].startswith("synthetic-stat-"):
            raise ValueError("fictional question IDs only")
        for field in ("eligibility", "clean"):
            if q[field] not in SCHEMA["frame_fields"][field]:
                raise ValueError("invalid frame state")
        ids.append(q["question_id"])
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate frame IDs")
    seen = set()
    for r in rows:
        if type(r) is not dict or set(r) != set(SCHEMA["row_fields"]):
            raise ValueError("invalid analysis row fields")
        if r["question_id"] not in ids:
            raise ValueError("unknown question ID")
        for field in ("family", "condition"):
            if not isinstance(r[field], str) or not r[field].strip():
                raise ValueError("invalid condition identity")
        key = tuple(r[f] for f in SCHEMA["row_identity"])
        if key in seen:
            raise ValueError("duplicate question/family/condition")
        seen.add(key)
        for field in ("construction", "retrieval", "generator", "outcome"):
            if r[field] not in SCHEMA["row_fields"][field]:
                raise ValueError("invalid outcome/exposure state")
        if r["construction"] != "SUCCEEDED" and r["outcome"] in RESOLVED:
            raise ValueError("resolved outcome requires successful construction")
    return True


def _member(q, row, population):
    if population == "fixed_frame":
        return True
    if q["eligibility"] in ("UNKNOWN", "NOT_REVIEWED"):
        return None
    if q["eligibility"] == "INELIGIBLE":
        return False
    if population == "eligible":
        return True
    if population == "clean_correct":
        return None if q["clean"] in ("MISSING", "NEEDS_REVIEW") else q["clean"] == "CORRECT"
    if row is None or row["construction"] in ("UNKNOWN", "NOT_ATTEMPTED"):
        return None
    if row["construction"] == "FAILED":
        return False
    if population == "constructed":
        return True
    if population == "judge_resolved":
        return row["outcome"] in RESOLVED
    field = "retrieval" if population == "retrieved" else "generator"
    value = row[field]
    return True if value == "YES" else False if value in ("NO", "NOT_APPLICABLE") else None


def _value(row):
    if (row is None or row["construction"] != "SUCCEEDED" or row["outcome"] not in RESOLVED
            or row["generator"] in ("TRUNCATED", "UNVERIFIED")):
        return None
    return int(row["outcome"] == "POISON_ADOPTED")


def _quantile(xs, p):
    xs = sorted(xs)
    index = (len(xs) - 1) * p
    a = int(index)
    return xs[a] + (xs[min(a + 1, len(xs) - 1)] - xs[a]) * (index - a)


def cluster_mean(clusters, *, seed=SEED, draws=2000):
    """Equal-question mean; each supplied cluster is one complete q contrast.

    Repeated rows are aggregated WITHIN each question before this interface.
    Never pass individual condition rows as separate clusters.
    """
    if type(clusters) is not dict or any(not isinstance(k, str) for k in clusters):
        raise ValueError("explicit question-keyed clusters required")
    if type(seed) is not int or type(draws) is not int or draws < 100:
        raise ValueError("integer seed and >=100 resamples required")
    values = [clusters[k] for k in sorted(clusters)]
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in values):
        raise ValueError("finite complete numeric question contrasts required")
    n = len(values)
    if not n:
        return {"status": "NOT_ESTIMABLE", "estimate": None, "ci95": None, "effective_questions": 0}
    point = sum(values) / n
    result = {"status": "DEFINED", "estimate": point, "effective_questions": n,
              "seed": seed, "resamples": draws, "method": "question-cluster percentile bootstrap",
              "assumption": "independent representative question clusters; paired rows retained",
              "warning": "SMALL_CLUSTER_COUNT" if n < 20 else None}
    if n < 2:
        return {**result, "ci95": None, "uncertainty_status": "NOT_ESTIMABLE_SINGLE_QUESTION"}
    rng = random.Random(seed)
    boot = [sum(rng.choice(values) for _ in range(n)) / n for _ in range(draws)]
    return {**result, "ci95": [_quantile(boot, .025), _quantile(boot, .975)],
            "uncertainty_status": "DEGENERATE_EMPIRICAL_DISTRIBUTION" if len(set(values)) == 1 else "APPROXIMATE"}


def rate(frame, rows, *, population, family, condition):
    validate(frame, rows)
    if population not in POPULATIONS:
        raise ValueError("unknown population")
    index = {r["question_id"]: r for r in rows if r["family"] == family and r["condition"] == condition}
    members, unknown, counts = [], [], Counter()
    for q in frame:
        r = index.get(q["question_id"])
        state = _member(q, r, population)
        counts["MISSING_ROW" if r is None else r["outcome"]] += 1
        if state is None:
            unknown.append(q["question_id"])
        elif state:
            members.append((q["question_id"], _value(r)))
    n = len(members)
    positives = sum(v == 1 for _, v in members)
    missing = sum(v is None for _, v in members)
    status = "NOT_ESTIMABLE" if unknown else "UNDEFINED" if n == 0 or missing else "DEFINED"
    return {"population": population, "family": family, "condition": condition, "status": status,
        "reason": "UNKNOWN_POPULATION_MEMBERSHIP" if unknown else "ZERO_DENOMINATOR" if n == 0 else "UNRESOLVED_OUTCOMES" if missing else None,
        "numerator_observed_adoptions": positives, "denominator_known_members": n,
        "denominator_established": not unknown, "unresolved_outcomes": missing,
        "unknown_membership_ids": unknown, "outcome_counts_full_frame": dict(sorted(counts.items())),
        "estimate": positives / n if status == "DEFINED" else None,
        "known_member_missingness_bounds": [positives / n, (positives + missing) / n] if n else None,
        "unknown_membership_sensitivity_bounds": [positives / (n + len(unknown)),
            (positives + missing + len(unknown)) / (n + len(unknown))] if n + len(unknown) else None,
        "uncertainty": cluster_mean(dict(members)) if status == "DEFINED" else None}


def exact_sign_flip(values):
    """Two-sided exact sign-flip test; exchangeability/symmetry is a proposal."""
    n = len(values)
    if n == 0 or n > 16:
        return None
    target = abs(sum(values))
    count = sum(abs(sum(x * sign for x, sign in zip(values, signs))) >= target - 1e-12
                for signs in product((-1, 1), repeat=n))
    return count / (2 ** n)


def paired_difference(frame, rows, *, families, neutral="neutral", freshness="freshness"):
    """Freshness minus neutral, equal questions and equal prespecified families.

    Any incomplete required pair makes the primary difference undefined.
    Complete-case estimates are deliberately not substituted.
    """
    validate(frame, rows)
    if type(families) is not list or not families or len(set(families)) != len(families) or neutral == freshness:
        raise ValueError("unique prespecified family list and distinct conditions required")
    index = {(r["question_id"], r["family"], r["condition"]): r for r in rows}
    clusters, incomplete, bounds, unknown = {}, [], [], []
    for q in frame:
        if q["eligibility"] in ("UNKNOWN", "NOT_REVIEWED"):
            unknown.append(q["question_id"])
            continue
        if q["eligibility"] != "ELIGIBLE":
            continue
        diffs, low, high = [], 0, 0
        for family in families:
            left, right = [_value(index.get((q["question_id"], family, c))) for c in (neutral, freshness)]
            low += (0 if right is None else right) - (1 if left is None else left)
            high += (1 if right is None else right) - (0 if left is None else left)
            if left is not None and right is not None:
                diffs.append(right - left)
        bounds.append((low / len(families), high / len(families)))
        if len(diffs) == len(families):
            clusters[q["question_id"]] = sum(diffs) / len(families)
        else:
            incomplete.append(q["question_id"])
    status = "NOT_ESTIMABLE" if unknown else "UNDEFINED" if incomplete or not bounds else "DEFINED"
    n = len(bounds)
    return {"status": status, "estimand": "equal-question, equal-family freshness-minus-neutral risk difference",
        "eligible_questions_known": n, "effective_complete_questions": len(clusters),
        "families": families, "unknown_eligibility_ids": unknown, "incomplete_pair_ids": incomplete,
        "estimate": sum(clusters.values()) / n if status == "DEFINED" else None,
        "missingness_bounds_known_eligible": [sum(b[i] for b in bounds) / n for i in (0, 1)] if n else None,
        "uncertainty": cluster_mean(clusters) if status == "DEFINED" else None,
        "p_value_proposed_sign_flip": exact_sign_flip(list(clusters.values())) if status == "DEFINED" else None}


FACTORS = ("date", "header", "order")
CELL_LEVELS = list(product((-1, 1), repeat=3))


def factorial_effects(frame, rows):
    """RQ3 levels: +1 incorrect-newer/freshness/incorrect-first.

    Main effect=sum(x*y)/4; two-way difference-in-differences=sum(x*x*y)/2;
    three-way difference of interactions=sum(x*x*x*y). Within-question first.
    """
    validate(frame, rows)
    index = {(r["question_id"], r["condition"]): r for r in rows if r["family"] == "rq3"}
    expected = {cell_name(x) for x in CELL_LEVELS}
    if any(r["family"] == "rq3" and r["condition"] not in expected for r in rows):
        raise ValueError("unsupported factorial cell")
    eligible = [q for q in frame if q["eligibility"] == "ELIGIBLE"]
    unknown = [q["question_id"] for q in frame if q["eligibility"] in ("UNKNOWN", "NOT_REVIEWED")]
    complete, incomplete = {}, []
    for q in eligible:
        cells = {x: index.get((q["question_id"], cell_name(x))) for x in CELL_LEVELS}
        if any(_value(r) is None or r["generator"] != "YES" for r in cells.values()):
            incomplete.append(q["question_id"])
        else:
            complete[q["question_id"]] = {x: _value(r) for x, r in cells.items()}
    status = "NOT_ESTIMABLE" if unknown or incomplete or not eligible else "DEFINED"
    effects = {}
    for k in (1, 2, 3):
        for positions in combinations(range(3), k):
            name = ":".join(FACTORS[i] for i in positions)
            clusters = {qid: sum(math.prod(x[i] for i in positions) * y for x, y in ys.items()) / (2 ** (3-k))
                        for qid, ys in complete.items()}
            effects[name] = {"estimate": sum(clusters.values()) / len(clusters) if status == "DEFINED" else None,
                "scale": "risk difference" if k == 1 else "difference of risk differences",
                "uncertainty": cluster_mean(clusters) if status == "DEFINED" else None,
                "p_value_proposed_sign_flip": exact_sign_flip(list(clusters.values())) if status == "DEFINED" else None}
    return {"status": status, "eligible_questions_known": len(eligible), "effective_complete_questions": len(complete),
            "incomplete_or_unverified_ids": incomplete, "unknown_eligibility_ids": unknown, "effects": effects}


def cell_name(levels):
    return "/".join(("incorrect_newer" if levels[0] == 1 else "correct_newer",
                     "freshness" if levels[1] == 1 else "neutral",
                     "incorrect_first" if levels[2] == 1 else "correct_first"))


def holm(p_values, *, family):
    """Proposed fixed family. Missing tests block the family, never shrink it."""
    if not family or len(family) != len(set(family)) or set(p_values) != set(family):
        raise ValueError("exact prespecified hypothesis family required")
    if any(p is None for p in p_values.values()):
        return {"status": "NOT_ESTIMABLE", "reason": "INCOMPLETE_PRESPECIFIED_FAMILY", "adjusted": None}
    if any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1 for p in p_values.values()):
        raise ValueError("invalid p-value")
    ordered = sorted(family, key=lambda h: (p_values[h], h))
    adjusted, running = {}, 0
    for i, h in enumerate(ordered):
        running = max(running, min(1, (len(family)-i) * p_values[h]))
        adjusted[h] = running
    return {"status": "DEFINED_PROPOSED_NOT_APPROVED", "order": ordered, "adjusted": adjusted,
            "method": "Holm step-down; ties by hypothesis ID"}


def planning_inputs(*, meaningful_difference=None, margin=None, paired_discordance=None, cluster_variance=None):
    return {"meaningful_absolute_difference": meaningful_difference, "noninferiority_margin": margin,
            "paired_discordance_probability": paired_discordance, "question_contrast_variance": cluster_variance,
            "additional_required_inputs": ["approved alpha and target power", "confirmatory family size",
                "paired discordant probabilities p01 and p10", "eligible/exposed/resolved fractions",
                "question-cluster variance or justified dependence model", "sampling/generalization target"],
            "sample_size": "NOT_ESTIMABLE_WITHOUT_APPROVED_TARGET_ALPHA_POWER_AND_VARIANCE_MODEL",
            "interpretation": "nonsignificance establishes neither equivalence nor noninferiority"}
