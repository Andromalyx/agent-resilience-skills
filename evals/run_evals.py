"""Minimal eval runner for starter JSONL datasets.

This runner checks that each case activates resilience and selects the expected
response pattern when an expected pattern is provided.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from runtime import assess_resilience


def run_dataset(path: Path) -> tuple[int, int]:
    passed = 0
    total = 0

    with path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            total += 1
            case = json.loads(line)
            result = assess_resilience(case["input"])
            expected_pattern = case.get("expected_pattern")
            ok = result.activated
            if expected_pattern:
                ok = ok and result.plan.response_pattern == expected_pattern
            passed += int(ok)

    return passed, total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path, default=sorted(Path("evals/datasets").glob("*.jsonl")))
    args = parser.parse_args()

    total_passed = 0
    total_cases = 0
    for path in args.paths:
        passed, count = run_dataset(path)
        total_passed += passed
        total_cases += count
        print(f"{path}: {passed}/{count}")

    if total_passed != total_cases:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
