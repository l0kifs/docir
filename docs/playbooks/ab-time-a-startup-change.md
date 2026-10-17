# A/B-time a startup or import change

**When:** you changed what docir imports or how fast its process starts, and the effect is below the ~0.15s noise `benchmarks/latency.py` documents.
**Instead of:** a `latency.py` run before and after the edit, or `min` of N sequential runs per side — both moved the wrong way for a real −90ms change, because laptop load drifts between the two passes.
**Status:** verified
**Last verified:** 2026-10-17

## Do
1. From the repo root, with the change in the working tree (uncommitted is fine):
   `uv run python docs/playbooks/scripts/ab_startup.py -- -m docir version`
2. For the import graph alone: `uv run python docs/playbooks/scripts/ab_startup.py -- -c "import docir.entry_points.cli.app"`.
3. Against something other than `HEAD` (a branch point, a release tag): add `--ref <ref>` before `--`.

## Verify
It prints one row per side with `p50`, `min` and `modules`, then a `delta` row. A real change moves `modules` and both `p50` and `min` in the same direction; a delta whose p50 and min disagree in sign is noise — rerun with `--runs 50`. Exit 1 with "PYTHONPATH did not select the worktree" means the comparison would have timed B against B.

## Pitfalls
- `docir --version` is not a flag: it exits 2 through Typer's rich error formatter, which imports `markdown_it` and `pygments`. Time `docir version`, the real floor command.
- Run it while nothing else heavy runs; interleaving cancels drift, not a CPU-bound neighbour that comes and goes within one pair.
- Never `git stash` to get the "before" side while the test suite runs: it rewrites `src/` mtimes, the daemon code stamp moves mid-test, and `test_a_live_daemon_on_other_code_is_replaced` fails. The worktree is why this script needs no stash.
- It measures whole processes, so it cannot see the daemon side of a command; for that, time `Dispatcher` calls in one warm process.
