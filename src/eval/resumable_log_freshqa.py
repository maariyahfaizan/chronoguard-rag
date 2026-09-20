"""
Resumable logging for the run_*_freshqa.py drivers.

Motivation: a full 477-question E1 run was lost in its entirety when a
Kaggle session ended before the log was saved, because every driver opened
its log with "w" and started from query_id=0 unconditionally. This module
fixes that: on startup, a driver reads back whatever's already in its log
file (if any), treats those query_ids as done, and appends only the
remaining ones -- so a session death mid-run loses at most the one
in-flight query, not the whole run.

Usage in a driver (replaces the old `results = []` / `groups = []` /
`with open(log_path, "w") as log_file:` block):

    from src.eval.resumable_log import load_existing_results

    results, groups, completed_ids = load_existing_results(log_path, group_key="fact_type")

    log_mode = "a" if completed_ids else "w"
    with open(log_path, log_mode) as log_file:
        for query_id, row in enumerate(rows):
            if query_id in completed_ids:
                continue
            ... existing per-query logic, unchanged ...
"""

import json
import os


def load_existing_results(log_path, group_key):
    """
    Reads log_path if it exists and returns (results, groups,
    completed_ids):
      - results: list of previously-logged record dicts, in file order.
      - groups: the group_key field (e.g. "fact_type") pulled from each
        of those records, in the same order -- so aggregate_metrics_by_group
        gets a complete groups list covering resumed rows too, not just
        newly-run ones.
      - completed_ids: set of query_id values already present, for the
        caller to skip in its main loop.

    If log_path doesn't exist yet, returns ([], [], set()) -- a normal
    fresh start, log_mode should be "w" in that case.

    Tolerates a truncated/corrupt LAST line (the realistic failure mode
    if a session died mid-write, since log_file.flush() is called after
    every complete record, but a process kill mid-write of the final line
    can still leave a partial one): skips only that unparseable trailing
    line with a warning, keeps everything before it. A corrupt line
    ANYWHERE ELSE in the file (not just the last) is treated as a hard
    error and raises, since that would indicate something worse than an
    interrupted run and silently discarding a middle record would corrupt
    the resumed results silently.
    """
    if not os.path.exists(log_path):
        return [], [], set()

    results = []
    groups = []
    completed_ids = set()

    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError as e:
            is_last_line = (i == len(lines) - 1) or all(
                not l.strip() for l in lines[i + 1:]
            )
            if is_last_line:
                print(
                    f"WARNING: {log_path} line {i + 1} (last line) is not valid "
                    f"JSON -- treating as a truncated write from an interrupted "
                    f"session and discarding it. That query will be re-run. "
                    f"({e})"
                )
                break
            raise ValueError(
                f"{log_path} line {i + 1} is not valid JSON, and it is NOT the "
                f"last line in the file -- this looks like real corruption, not "
                f"just an interrupted final write, so refusing to silently "
                f"resume over it. Inspect the file by hand. ({e})"
            )

        results.append(record)
        groups.append(record.get(group_key))
        completed_ids.add(record["query_id"])

    if completed_ids:
        print(
            f"Resuming {log_path}: {len(completed_ids)} queries already "
            f"completed, skipping them."
        )

    return results, groups, completed_ids