#!/usr/bin/env python3
"""Agreement statistics for FreshQA judge validation (Gate B item 9).

Reads (from DIR):
    annotation.csv         your labels (human_label = 1/0)
    key.csv                judge_label (Mistral), optional judge2_label, system, stratum
    annotation_rater2.csv  optional: labels from a second human on a subset

Reports raw agreement, Cohen's kappa with a bootstrap 95% CI, accuracy of each rater,
both error directions with an exact sign test (is one rater systematically more lenient?),
and per-stratum and per-system breakdowns for each judge.

    python scripts/judge_validation_agreement.py
"""
import csv
import random
from math import comb
from pathlib import Path

DIR = Path("results/judge_validation")
N_BOOT = 2000


def read(path):
    return list(csv.DictReader(open(path, encoding="utf-8-sig")))


def to_bin(v, where):
    v = str(v).strip()
    if v not in ("0", "1"):
        raise ValueError(f"{where}: label must be 0 or 1, got {v!r}")
    return int(v)


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return po, ((po - pe) / (1 - pe) if pe < 1 else float("nan"))


def kappa_ci(a, b, seed=0):
    rng = random.Random(seed)
    n = len(a)
    ks = []
    for _ in range(N_BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        _, k = kappa([a[i] for i in idx], [b[i] for i in idx])
        if k == k:  # drop NaN (resample with no variation)
            ks.append(k)
    ks.sort()
    if not ks:
        return float("nan"), float("nan")
    return ks[int(0.025 * len(ks))], ks[int(0.975 * len(ks)) - 1]


def sign_test_p(b, c):
    """Exact two-sided sign test on the discordant pairs (b vs c)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def report(name_a, name_b, a, b):
    n = len(a)
    po, k = kappa(a, b)
    lo, hi = kappa_ci(a, b)
    lenient = sum(x == 0 and y == 1 for x, y in zip(a, b))
    strict = sum(x == 1 and y == 0 for x, y in zip(a, b))
    print(f"\n{name_a} vs {name_b}  (n={n})")
    print(f"  agreement = {po:.3f}   kappa = {k:.3f}   95% CI [{lo:.3f}, {hi:.3f}]")
    print(f"  accuracy: {name_a} = {sum(a)/n:.3f}   {name_b} = {sum(b)/n:.3f}")
    print(f"  {name_b} correct / {name_a} wrong: {lenient}")
    print(f"  {name_b} wrong / {name_a} correct: {strict}")
    print(f"  disagreement split {lenient} vs {strict}: exact sign-test p = {sign_test_p(lenient, strict):.4f}"
          f"  (small p = {name_b} is systematically more lenient or strict than {name_a})")
    if k == k and po > 0.9 and k < 0.6:
        print("  note: high agreement with low kappa usually means one class dominates; read both numbers.")


def breakdown(name, human, judge, strata, systems):
    print(f"\nper stratum (human vs {name}):")
    for s in sorted(set(strata)):
        idx = [i for i, x in enumerate(strata) if x == s]
        p, k = kappa([human[i] for i in idx], [judge[i] for i in idx])
        print(f"  {s:15s} n={len(idx):3d}  agreement={p:.3f}  kappa={k:.3f}")
    print(f"\nper system (human vs {name}):")
    for s in sorted(set(systems)):
        idx = [i for i, x in enumerate(systems) if x == s]
        p, k = kappa([human[i] for i in idx], [judge[i] for i in idx])
        print(f"  {s:20s} n={len(idx):3d}  agreement={p:.3f}  kappa={k:.3f}  "
              f"human acc={sum(human[i] for i in idx)/len(idx):.3f}  "
              f"judge acc={sum(judge[i] for i in idx)/len(idx):.3f}")


def main():
    key = {r["item_id"]: r for r in read(DIR / "key.csv")}
    ann = [r for r in read(DIR / "annotation.csv") if r["human_label"].strip() != ""]
    total = len(read(DIR / "annotation.csv"))
    print(f"labelled {len(ann)} of {total} items")
    if not ann:
        raise SystemExit("No labels yet.")
    if len(ann) < 100:
        print("WARNING: fewer than 100 labelled items; the supervisor asked for at least 100.")

    human = [to_bin(r["human_label"], f"annotation item {r['item_id']}") for r in ann]
    j1 = [to_bin(key[r["item_id"]]["judge_label"], "key judge_label") for r in ann]
    strata = [key[r["item_id"]]["stratum"] for r in ann]
    systems = [key[r["item_id"]]["system"] for r in ann]

    report("human", "judge1(Mistral)", human, j1)
    breakdown("judge1", human, j1, strata, systems)

    # optional: second judge
    has_j2 = [r for r in ann if key[r["item_id"]].get("judge2_label", "").strip() != ""]
    if has_j2:
        h2 = [to_bin(r["human_label"], "") for r in has_j2]
        a2 = [to_bin(key[r["item_id"]]["judge2_label"], "key judge2_label") for r in has_j2]
        m1 = [to_bin(key[r["item_id"]]["judge_label"], "") for r in has_j2]
        report("human", "judge2", h2, a2)
        report("judge1(Mistral)", "judge2", m1, a2)
        breakdown("judge2", h2, a2,
                  [key[r["item_id"]]["stratum"] for r in has_j2],
                  [key[r["item_id"]]["system"] for r in has_j2])

        e1 = sum(h != m for h, m in zip(h2, m1))
        e2 = sum(h != a for h, a in zip(h2, a2))
        only1 = sum(h != m and h == a for h, m, a in zip(h2, m1, a2))
        only2 = sum(h != a and h == m for h, m, a in zip(h2, m1, a2))
        print(f"\nwhich judge is closer to the human? judge1 errors={e1}, judge2 errors={e2}")
        print(f"  errors only judge1 makes: {only1}   errors only judge2 makes: {only2}   "
              f"exact sign-test p = {sign_test_p(only1, only2):.4f}")
        print("\nheadline accuracy on the sample:")
        print(f"  human={sum(h2)/len(h2):.3f}  judge1={sum(m1)/len(m1):.3f}  judge2={sum(a2)/len(a2):.3f}")
    else:
        print("\n(no judge2_label values in key.csv yet)")

    # optional: second human rater
    r2p = DIR / "annotation_rater2.csv"
    if r2p.exists():
        r2 = {r["item_id"]: r for r in read(r2p) if r["human_label"].strip() != ""}
        both = [r for r in ann if r["item_id"] in r2]
        if both:
            a = [to_bin(r["human_label"], "") for r in both]
            b = [to_bin(r2[r["item_id"]]["human_label"], "rater2") for r in both]
            report("human", "rater2", a, b)
        else:
            print("\n(annotation_rater2.csv has no labels yet)")


if __name__ == "__main__":
    main()