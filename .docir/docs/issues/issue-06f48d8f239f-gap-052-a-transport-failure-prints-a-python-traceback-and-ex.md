---
created: '2026-07-30'
description: Every client-side daemon error escapes the CLI's error mapping, so the
  default execution mode reports failure as a stack trace.
id: issue-06f48d8f239f
owner: maintainer
related:
- ref-cb2beaa41604
- arch-3e305bc76ff0
status: resolved
tags:
- daemon
- material
title: GAP-052 — a transport failure prints a Python traceback and exits 1 instead
  of the error it raised
type: issue
updated: '2026-07-30'
---

# GAP-052 — a transport failure prints a Python traceback and exits 1 instead of the error it raised

**Class:** incorrect · **Severity:** material · **Confidence:** observed
**Flow:** FLOW-001/FLOW-002 (every command dispatched over the daemon)
**Frequency:** every transport failure — unreachable daemon, daemon that will not start, unanswered request

## Finding

`runner.execute` wraps only the *construction* of the executor in `run_local`, which is
what maps a `DocirError` onto its exit code. The dispatch call itself sits outside that
handler, so any `DocirError` raised client-side by the transport — `DaemonError`,
`DaemonTimeoutError`, or `ensure_running`'s "daemon failed to become ready in time" —
propagates out of Typer as an unhandled exception.

## What happens today

OBSERVED. `DOCIR_REQUEST_TIMEOUT=0.001 docir add --type decision --title T --description d`
prints a full Python traceback ending in
`docir.platform.errors.DaemonTimeoutError: the daemon did not answer 'add' within 0.001s...`
and exits **1**. The message is correct and carefully worded; the user never sees it as a
message, and the exit code is not the 7 that `DaemonError` declares.

Errors *returned by* the daemon are unaffected — they come back as a `Response` carrying an
error payload and go through `_unwrap`, which exits with the right code. That is why this
survived: the daemon path normally either succeeds or returns a structured error, and only
a failure of the transport itself takes the broken branch.

## Impact

The mode every user runs by default reports its failures as a stack trace. A machine where
the daemon cannot start — the case `ensure_running` raises for — gets a traceback rather
than "daemon failed to become ready in time", and a script branching on exit code 7 sees 1.
It also undoes the message written for GAP-051 four commits earlier: the escape hatches it
names (`docir daemon status`, `DOCIR_REQUEST_TIMEOUT`, `--no-daemon`) are buried under a
traceback.

The docstring of `execute` describes fixing exactly this class of bug for schema loading —
"Left unwrapped, that surfaced as a raw Python traceback and exit 1 while `docir schema
validate` ... printed a clean message and exit 3" — and the fix was applied to the
construction path only, one line above the call that still needs it.

## Proposed default

Move the dispatch inside the same handler: wrap `executor.execute(...)` (and `_unwrap`) in
`run_local`, or catch `DocirError` around the whole body of `execute`. Add a regression
test that asserts a raised `DaemonError` produces a rendered message and exit 7 rather than
a traceback — injecting the bug to confirm the guard fails without the fix.

## Actors affected

- AI coding agent
- repository maintainer
- CI job

## Evidence

- `src/docir/entry_points/cli/runner.py` (`execute`, `run_local`)
- `src/docir/platform/transport/client.py` (`send`)
- PROBE-D4 in the 2026-07-30 probe log

## Resolution

FIXED 2026-07-30. `runner.execute` now wraps the dispatch in `run_local` as well as the construction, so a `DocirError` raised client-side by the transport is rendered and mapped onto its exit code like every other domain error. Replaying PROBE-D4: `DOCIR_REQUEST_TIMEOUT=0.001 docir add` now prints `error: the daemon did not answer 'add' within 0.001s...` and exits **7**, where it printed a traceback and exited 1. Errors the daemon *returns* are untouched — they still arrive as a `Response` and go through `_unwrap` — and a test pins that path so the fix cannot regress it. Verified by injecting the bug: with the dispatch moved back outside the handler, two of the three new guards fail. Pinned by `TestTransportErrorsReachTheUser`.
