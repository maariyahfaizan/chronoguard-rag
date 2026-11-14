#!/usr/bin/env python3
"""W6-J1 offline judge-v2 integration; registered synthetic fixtures only."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.eval.attack_postprocess_v2 import (
    fixture_bundle, read, run, verify_file_output, write_new,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rubric", required=True, help="Explicit v2 rubric; no fallback")
    commands = parser.add_subparsers(dest="command", required=True)
    fixture = commands.add_parser("fixtures")
    fixture.add_argument("--output", type=Path, required=True)
    process = commands.add_parser("process")
    process.add_argument("--input", type=Path, required=True)
    process.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--input", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from src.eval.answer_judge_v2 import RUBRIC_VERSION
    if args.rubric != RUBRIC_VERSION:
        parser.error("explicit supported v2 rubric required; no fallback")
    try:
        if args.command == "fixtures":
            write_new(args.output, fixture_bundle())
        elif args.command == "process":
            run(args.input, args.output, rubric_version=args.rubric)
        else:
            verify_file_output(read(args.output), args.input, rubric_version=args.rubric)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"W6-J1 rejected: {exc}\n")
    print("W6-J1 synthetic engineering check complete; scientific validation NOT_VALIDATED")


if __name__ == "__main__":
    main()
