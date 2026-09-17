# Prove a guard by injecting the bug it claims to catch

**When:** you wrote or changed a test that guards a behaviour or a piece of prose and CLAUDE.md's rule applies: a test that has never failed has not been shown to work.
**Instead of:** editing the source by hand to break it, running pytest, reading the output, and editing it back — once per guard, with the restore forgotten under a failure.
**Status:** verified
**Last verified:** 2026-09-17

## Do
1. Write `cases.json`, one object per guard: `{"label": "...", "path": "src/...", "old": "<exact text>", "new": "<the bug>", "test": "tests/.../test_x.py::test_name"}`. `old` must occur exactly once in `path`.
2. `python3 docs/playbooks/scripts/prove_guard.py cases.json`
3. A `MISSED` line means the guard does not see that bug: widen the assertion or the surface it reads, then rerun. Delete `cases.json` afterwards, or keep it in the scratchpad; it is not committed.

## Verify
Every line reads `CAUGHT <label>: ['1 failed in …']` and the last line is `all guards proven` with exit 0. `git status` shows no change the script made: each file is restored in a `finally`, even when pytest itself errors.

## Pitfalls
- Inject the bug the guard is *for*, not a syntax error: a test that fails because the module no longer imports proves nothing about the assertion.
- Pick a `test` narrow enough that the run is seconds; the whole file is fine, the whole suite is not.
- `old` that also occurs in a comment or docstring makes the count 2 and the case is skipped; include enough context to make it unique.
- The script runs `uv run pytest -p no:tach`; the tach plugin only does impact analysis and is off here so the run is deterministic.
