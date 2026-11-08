"""Week 4 v2 only. Default is read-only package verification, without models."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.eval.streamingqa_v2_experiment import A15_SHA256, SYSTEMS, execute, load_pool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--expected-manifest-sha256", default=A15_SHA256)
    parser.add_argument("--execute", action="store_true",
                        help="Explicitly authorize model execution; absent means validation only")
    parser.add_argument("--system", choices=SYSTEMS)
    parser.add_argument("--run-name")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.execute:
        if not args.system or not args.run_name:
            parser.error("--execute requires --system and --run-name")
        print(execute(args.package, args.run_name, args.system,
                      expected_manifest_sha256=args.expected_manifest_sha256, limit=args.limit))
    else:
        envelopes, manifest = load_pool(args.package, args.expected_manifest_sha256)
        print(json.dumps({"status": "VERIFIED_READ_ONLY", "questions": len(envelopes),
                          "manifest_sha256": args.expected_manifest_sha256,
                          "counts": manifest["expected_counts"],
                          "scientific_approval": "NOT_GRANTED"}))


if __name__ == "__main__":
    main()
