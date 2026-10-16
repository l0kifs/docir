#!/usr/bin/env python3
"""Prove a test guards what it claims: inject the bug, run the test, restore the file.

usage: prove_guard.py <cases.json>

cases.json is a list of {"label", "path", "old", "new", "test"}: `old` must occur exactly
once in `path`; it is replaced by `new`, `test` (a pytest node id or file, or a list of them)
is run, and the file is restored whatever happens. A case passes when a test FAILS under the
injection — pytest exit 1, and only that: exit 4 (a node id that does not exist) or 5 (nothing
collected) means no assertion ran, which is the false pass this script exists to rule out.
Exit 0 only when every case passes; a guard the injection did not trip is printed MISSED.
"""

import json
import subprocess
import sys
from pathlib import Path

#: pytest's exit code for "tests were collected and ran, and some failed".
TESTS_FAILED = 1


def prove(case: dict) -> bool:
    path = Path(case["path"])
    original = path.read_text(encoding="utf-8")
    if original.count(case["old"]) != 1:
        print(f"SKIP   {case['label']}: old text must occur exactly once in {path}")
        return False
    tests = case["test"] if isinstance(case["test"], list) else [case["test"]]
    path.write_text(original.replace(case["old"], case["new"]), encoding="utf-8")
    try:
        run = subprocess.run(
            ["uv", "run", "pytest", "-q", "-p", "no:tach", *tests],
            capture_output=True,
            text=True,
        )
    finally:
        path.write_text(original, encoding="utf-8")
    lines = run.stdout.splitlines()
    summary = [line for line in lines if "passed" in line or "failed" in line][-1:]
    caught = run.returncode == TESTS_FAILED
    verdict = "CAUGHT" if caught else "MISSED"
    print(f"{verdict} {case['label']}: {summary or f'pytest exit {run.returncode}'}")
    return caught


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    cases = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    results = [prove(case) for case in cases]
    print("all guards proven" if all(results) else "A GUARD DID NOT FIRE")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
