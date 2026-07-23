#!/usr/bin/env python3
"""Contract-sync gate (architecture-rules.md §7, §8.6).

Every module's public surface (``api.py``) and its ``CONTRACT.md`` must change
together. A diff that touches one without the other is rejected: the contract
is the executable-adjacent description callers rely on, so it may never drift
from the surface it documents.

Base selection (first that resolves):
  1. ``$CONTRACT_SYNC_BASE`` — explicit base ref.
  2. ``origin/$GITHUB_BASE_REF`` — the PR target branch, in CI.
  3. ``origin/main`` — the default remote branch.
  4. ``HEAD~1`` — the previous commit (single-commit fallback).

Working-tree (uncommitted) changes are always included, so the check also runs
usefully as a pre-commit hook. Exits non-zero on any unpaired change.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

API_NAME = "api.py"
CONTRACT_NAME = "CONTRACT.md"


def _run(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return result.stdout


def _ref_exists(ref: str) -> bool:
    return _run("rev-parse", "--verify", "--quiet", ref) is not None


def _resolve_base() -> str | None:
    explicit = os.environ.get("CONTRACT_SYNC_BASE")
    if explicit and _ref_exists(explicit):
        return explicit
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if base_ref and _ref_exists(f"origin/{base_ref}"):
        return f"origin/{base_ref}"
    if _ref_exists("origin/main"):
        return "origin/main"
    if _ref_exists("HEAD~1"):
        return "HEAD~1"
    return None


def _changed_files(base: str | None) -> set[str]:
    changed: set[str] = set()
    # Committed changes since the base.
    if base is not None:
        committed = _run("diff", "--name-only", f"{base}...HEAD") or ""
        changed.update(line for line in committed.splitlines() if line)
    # Uncommitted (staged + unstaged) changes.
    working = _run("status", "--porcelain") or ""
    for line in working.splitlines():
        # Format: "XY <path>" (or "XY <old> -> <new>" for renames).
        path = line[3:].split(" -> ")[-1].strip()
        if path:
            changed.add(path)
    return changed


def main() -> int:
    base = _resolve_base()
    changed = _changed_files(base)

    api_files = {p for p in changed if Path(p).name == API_NAME}
    violations: list[str] = []
    for api in sorted(api_files):
        contract = str(Path(api).with_name(CONTRACT_NAME))
        if contract not in changed:
            violations.append(f"{api} changed without {contract}")

    if violations:
        print("Contract-sync check FAILED (ARCHITECTURE_RULES §8.6):", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        print(
            "\nEvery change to a module's api.py must update its CONTRACT.md in the same change.",
            file=sys.stderr,
        )
        return 1

    print(f"Contract-sync OK ({len(api_files)} api.py file(s) checked against base {base}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
