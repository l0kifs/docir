---
created: '2026-08-05'
description: Nothing compares the running daemon's version against the installed one;
  after an upgrade or a source edit every command is answered by the old code, and
  the wrong answer looks normal.
id: issue-aaa512e9c58f
owner: maintainer
related:
- arch-0a3c2d6d54a6
- issue-44875a5a6ca6
status: resolved
tags:
- daemon
- material
title: The daemon keeps serving the code it started with, so a fix silently does not
  take effect
type: issue
updated: '2026-08-06'
---

**Class:** missing · **Severity:** material
**Flow:** arch-0a3c2d6d54a6 · **Step:** any command, after an upgrade or an edit to `src/`

## Finding

The daemon loads docir's code once and lives on (idle timeout, default 900s). Nothing
compares the running process's version against the installed one, so after an upgrade —
`uv sync`, a `pip install -U`, or any edit to `src/` during development — the client keeps
routing every command to a process running the *old* code, and the answer looks entirely
normal.

## What happens today

OBSERVED, during the fix for issue-44875a5a6ca6. `_find_cycles` was corrected and its unit
tests passed. `docir check` then reported **117 cycle findings**; `docir --no-daemon check`
reported **0**. The difference was a daemon started before the edit. Nothing in either
output indicated which code produced it, and the plausible reading of 117 findings is that
the fix is wrong — the failure imitates a real result rather than announcing itself.

`docir daemon status` prints the socket path and says nothing about the version being
served, so the state is not even inspectable after the fact. The workaround, once you
suspect it, is `docir daemon stop`.

## Impact

Every read is answered by the stale process, so a corrected check, a changed ranking or a
new schema rule silently does not take effect. The blast radius is bounded by the idle
timeout, which is exactly long enough to cover an edit-test cycle. It hits developers of
docir hardest and users of docir on the release where the behaviour changed.

## Proposed direction

Stamp the daemon's `docir.__version__` (and, in a development install, the mtime of the
loaded package) into the pid file at startup. The client already respawns on a refused
connect; have it also treat a version mismatch as a reason to stop and respawn, which
makes the recovery automatic rather than a thing you have to know. Failing that, print the
served version in `docir daemon status` so the state is at least visible.

## Resolution

FIXED. The pid file now carries a **code stamp** — `docir.__version__` plus the
newest mtime across the package's `.py` sources — and `ensure_running` stops and
replaces a live daemon whose stamp is not the client's. Recovery is automatic
rather than a thing you have to suspect and then fix with `docir daemon stop`.

The mtime half is not decoration: nothing bumps `__version__` between commits, so
a source edit during development — the case that produced the 117 cycles above —
is invisible to a version comparison. An installed wheel stamps its files at
install time, so the same pair also moves on `uv sync` / `pip install -U`; one
mechanism covers both. The walk costs ~10ms against a ~800ms CLI startup.

`current_stamp()` is cached per process, and that is what makes the daemon's
answer honest: it must report the build it *started with*, not whatever is on
disk when someone asks. A pid file written before the stamp existed holds a bare
integer — an unknown build, which never matches. That is correct rather than
lenient: such a daemon predates the check and is exactly what it exists to
replace.

`docir daemon status` now prints the served build (`serving 0.9.0`) and marks a
stale one, so the state is inspectable after the fact instead of only inferable
from an answer that looks wrong.

One thing the fix needed that the proposed direction did not name: `stop()` had
to start waiting for the process to actually exit. Its teardown clears the pid
file and unlinks the socket, so a replacement spawned while it was still winding
down could have both removed out from under it — a healthy daemon that no client
can find. Stop-then-immediately-spawn is a much tighter race than the paths that
existed before.

Verified by injecting the bug: reverting `ensure_running` to its old body fails
four tests, including `TestRealDaemon::test_a_live_daemon_on_other_code_is_replaced`,
which spawns a real detached daemon, doctors its recorded stamp and asserts the
next command answers from a different pid. Also confirmed by hand: start a daemon,
`touch src/docir/entry_points/cli/app.py`, and `daemon status` reports stale code,
after which any command replaces the process.
