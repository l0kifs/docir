#!/usr/bin/env python3
"""Prove a test guards what it claims: inject the bug, run the test, restore the file.

usage: prove_guard.py <cases.json>

cases.json is a list of {"label", "path", "old", "new", "test"}: `old` must occur exactly
once in `path`; it is replaced by `new`, `test` (a pytest node id or file) is run, and the
file is restored whatever happens. A case passes when the test FAILS under the injection.
Exit 0 only when every case passes; a guard the injection did not trip is printed MISSED.
"""

import json
import subprocess
import sys
from pathlib import Path


def prove(case: dict) -> bool:
    path = Path(case["path"])
    original = path.read_text(encoding="utf-8")
    if original.count(case["old"]) != 1:
        print(f"SKIP   {case['label']}: old text must occur exactly once in {path}")
        return False
    path.write_text(original.replace(case["old"], case["new"]), encoding="utf-8")
    try:
        run = subprocess.run(
            ["uv", "run", "pytest", "-q", "-p", "no:tach", case["test"]],
            capture_output=True,
            text=True,
        )
    finally:
        path.write_text(original, encoding="utf-8")
    lines = run.stdout.splitlines()
    summary = [line for line in lines if "passed" in line or "failed" in line][-1:]
    caught = run.returncode != 0
    print(f"{'CAUGHT' if caught else 'MISSED'} {case['label']}: {summary}")
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
