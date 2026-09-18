---
code:
- src/docir/entry_points/daemon/lifecycle.py
- src/docir/entry_points/daemon/cmds.py
- src/docir/entry_points/doctor.py
code_baseline:
  src/docir/entry_points/daemon/cmds.py: f1efcea6c68c
  src/docir/entry_points/daemon/lifecycle.py: 3e55861fc705
  src/docir/entry_points/doctor.py: ce032a47b5e6
created: '2026-09-18'
description: Both read Settings.socket_path directly to report it, so the sandbox
  that made every dispatched command fall back still ends these two in a traceback.
id: issue-b9800d8265f6
owner: maintainer
related:
- issue-c4c6349e06d4
- arch-1cfb1b212237
status: resolved
tags:
- cli
- daemon
title: doctor and daemon status still crash where the daemon has nowhere to listen
type: issue
updated: '2026-09-18'
verified: '2026-09-18'
verified_code:
  src/docir/entry_points/daemon/cmds.py: f1efcea6c68c
  src/docir/entry_points/daemon/lifecycle.py: 3e55861fc705
  src/docir/entry_points/doctor.py: ce032a47b5e6
verified_content: 7663e5b8a7d5
---

## What is wrong

`Settings.socket_path` asks `tempfile.gettempdir()` for somewhere to put the daemon's
socket, and that raises where no temporary directory is usable — a read-only sandbox,
which is the environment the daemon fallback exists for.

Every command that *dispatches* survives it: the executor catches it and runs in
process ([[issue-c4c6349e06d4]]). The two that do not dispatch read the path directly
to report it — `docir doctor` through its pre-dispatch environment snapshot, and
`docir daemon status` — so both still end in a traceback.

They are the commands somebody runs *to diagnose* the first failure. The warning on
stderr says the daemon could not be started; the report that would explain why crashes.

## Measured

The reporter's original traceback was `FileNotFoundError: No usable temporary
directory`, raised from `docir get` before the fallback existed. With the fallback, the
same environment answers every read and `docir doctor` still raises from
`lifecycle.status`, which calls `settings.socket_path` twice — once through `is_running`
and once to report it.

Recorded as "Left open" when the fallback shipped, because closing it means deciding
what `DaemonStatus.socket_path` reports when there is no path to report — a change to a
field rather than a `try`.

## What would fix it

`DaemonStatus.socket_path` becomes `str | None`, and `None` means *a daemon cannot exist
here*, which is a different fact from "it is not running". `daemon status` says so
instead of "not running", which would send the caller round a loop nothing in the
environment can close, and `doctor` reports `no-daemon-socket` as a **warning**: every
command works, in process, so `--strict` must not fail a setup that is merely slow.

`daemon serve` is the one caller that keeps raising. A client without a socket runs in
process; a server with nowhere to bind is not a degraded daemon.

## Resolution

FIXED 2026-09-18. `lifecycle.socket_path` answers `None` where the platform offers nowhere
to put a socket, and `DaemonStatus.socket_path` carries that through. `None` means *a
daemon cannot exist here*, which is a different fact from "it is not running" and is
reported as one: `daemon status` says it cannot run here, and `doctor` raises
`no-daemon-socket` as a **warning** with the two exits, `TMPDIR` or `DOCIR_NO_DAEMON=1`.

A warning because every command still answers. An error would fail `--strict` on a setup
that works and is merely slow, which is the promotion [[adr-bd7c4f3c5764]] argues against
one tier down.

`daemon serve` is the one caller that keeps raising, and it now renders the refusal through
`run_local` like every other non-dispatching command instead of escaping as a traceback —
the client quotes the daemon's log when it will not come up, and a traceback there buries
the sentence naming the cause.

Exercised against this repository's own 233-document corpus with `tempfile.gettempdir()`
made to raise:

```
daemon status    cannot run here — no usable temporary directory for the socket
doctor --strict  ok: true, one no-daemon-socket warning, exit 0
```

and unchanged where a socket can exist: the path is reported and no finding is raised.

Four injections, each proven to fail its guard: letting the `OSError` through again, falling
back to "not running", making the finding an error, and having `serve` invent a path.

## What is still not survivable here

With **no** temporary directory at all, `fastembed` raises computing its own default cache
directory, so `query`, `get` and `search` still fail — inside the library, before docir
runs. `check`, `doctor` and `daemon status` work, which is what makes the situation
diagnosable, and that is the whole of what this issue claimed.

The reported environment was milder than this: writes to `TMPDIR` were denied but reads
answered, and `--no-daemon get` worked there. Pointing `FASTEMBED_CACHE_PATH` inside the
store would close the harsher case, and is a decision about where a downloaded model lives
rather than a `try` — not taken here.
