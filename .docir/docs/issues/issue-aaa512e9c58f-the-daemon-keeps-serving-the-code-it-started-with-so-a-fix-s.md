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
status: open
tags:
- daemon
- material
title: The daemon keeps serving the code it started with, so a fix silently does not
  take effect
type: issue
updated: '2026-08-05'
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
