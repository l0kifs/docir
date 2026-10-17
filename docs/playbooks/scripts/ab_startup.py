#!/usr/bin/env python3
"""Interleaved A/B of whole Python processes: a git ref (A) against the working tree (B).

Usage (from the repo root, so the interpreter is the project's venv):

    uv run python docs/playbooks/scripts/ab_startup.py [--ref HEAD] [--runs 25] -- -m docir version
    uv run python docs/playbooks/scripts/ab_startup.py -- -c "import docir.entry_points.cli.app"

A is the ref checked out into a throwaway worktree and put first on PYTHONPATH,
which outranks the editable install's .pth entry; B is the working tree. Same
interpreter, same site-packages, so the only variable is docir's own source.
Samples alternate A, B, A, B so machine load drifts onto both sides equally —
sequential before/after runs on a laptop wander by more than an import change.
"""

from __future__ import annotations

import argparse
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# One untimed run per side first: the fresh worktree has no __pycache__, so its
# first import compiles bytecode and would make A look slower than it is.
WARMUP_RUNS = 1


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def _timed(argv: list[str], env: dict[str, str]) -> float:
    start = time.perf_counter()
    subprocess.run(argv, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return time.perf_counter() - start


def _modules(argv: list[str], env: dict[str, str]) -> int:
    traced = [argv[0], "-X", "importtime", *argv[1:]]
    probe = subprocess.run(traced, env=env, capture_output=True, text=True, check=False)
    rows = [line for line in probe.stderr.splitlines() if line.startswith("import time:")]
    return len(rows) - 1  # the first row is the column header


def _row(label: str, times: list[float], modules: int) -> str:
    p50, fastest = statistics.median(times), min(times)
    return f"{label:>12}  p50 {p50:.3f}s  min {fastest:.3f}s  modules {modules}"


def _origin(env: dict[str, str]) -> str:
    probe = [sys.executable, "-c", "import docir; print(docir.__file__)"]
    return subprocess.run(probe, env=env, capture_output=True, text=True, check=True).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--runs", type=int, default=25)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="interpreter arguments after --")
    args = parser.parse_args()
    command = [part for part in args.command if part != "--"]
    if not command:
        parser.error("give the interpreter arguments after --, e.g. -- -m docir version")
    argv = [sys.executable, *command]

    root = Path(_git("rev-parse", "--show-toplevel"))
    worktree = Path(tempfile.mkdtemp(prefix="ab-startup-")) / "ref"
    _git("-C", str(root), "worktree", "add", "--quiet", "--detach", str(worktree), args.ref)
    try:
        env_b = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        env_a = {**env_b, "PYTHONPATH": str(worktree / "src")}
        if not _origin(env_a).startswith(str(worktree)):
            print(f"PYTHONPATH did not select the worktree: {_origin(env_a)}", file=sys.stderr)
            return 1
        for _ in range(WARMUP_RUNS):
            _timed(argv, env_a)
            _timed(argv, env_b)
        a, b = [], []
        for _ in range(args.runs):
            a.append(_timed(argv, env_a))
            b.append(_timed(argv, env_b))
        print(f"command: {' '.join(command)}   pairs: {args.runs}")
        print(_row(args.ref, a, _modules(argv, env_a)))
        print(_row("working tree", b, _modules(argv, env_b)))
        p50_delta = statistics.median(b) - statistics.median(a)
        print(f"{'delta':>12}  p50 {p50_delta:+.3f}s  min {min(b) - min(a):+.3f}s")
    finally:
        _git("-C", str(root), "worktree", "remove", "--force", str(worktree))
    return 0


if __name__ == "__main__":
    sys.exit(main())
