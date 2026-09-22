---
code:
- src/docir/entry_points/cli/runner.py
- src/docir/entry_points/daemon/lifecycle.py
code_baseline:
  src/docir/entry_points/cli/runner.py: 66abea831942
  src/docir/entry_points/daemon/lifecycle.py: 3e55861fc705
created: '2026-09-18'
description: The client spawns the daemon on first dispatch and has no fallback, so
  a sandbox that denies the socket or log directory turns every read into a traceback
  — though --no-daemon answers the same read.
id: issue-c4c6349e06d4
owner: maintainer
related:
- arch-1cfb1b212237
- issue-b9800d8265f6
- adr-78090be868ec
status: resolved
tags:
- cli
- daemon
title: A daemon that cannot be started fails the command instead of running in process
type: issue
updated: '2026-09-22'
verified: '2026-09-22'
verified_code:
  src/docir/entry_points/cli/runner.py: 66abea831942
  src/docir/entry_points/daemon/lifecycle.py: 3e55861fc705
verified_content: 57d0bbaf24d0
---

## What is wrong

The daemon is an accelerator — it keeps the model warm and serializes writes —
and every read it serves, `--no-daemon` serves too. But a client that cannot
*start* one does not fall back to running in process: it fails, and where the
failure is an `OSError` rather than a `DaemonError` it fails as a raw traceback.

`SocketExecutor.execute` calls `ensure_running` on each request, so the failure
lands inside dispatch, past the point `run_local` maps a typed error onto an
exit code. `spawn` reaches the filesystem three times — `ensure_directories`,
opening `daemon.log`, `subprocess.Popen` — and `settings.socket_path` reaches
`tempfile.gettempdir()`, which raises when no temporary directory is usable.
None of those are `DocirError`.

## Measured

Reported from an OpenAI Codex `codex exec -s read-only` session: `TMPDIR` names
a path the sandbox denies writes to, so `tempfile.gettempdir()` raises and
`docir get` ends in `FileNotFoundError: No usable temporary directory`. The same
command with `--no-daemon` answers normally.

Reproduced here without a sandbox, by making the log file unopenable — the same
shape, a spawn that cannot touch the filesystem:

```
mkdir .docir/daemon.log            # now a directory
docir add ...                      # IsADirectoryError, traceback, from spawn()
docir --no-daemon query            # answers
```

## Why it matters

This is the shape an agent gate runs in: an independent reviewer reads the
repository read-only. The reporter's followed the installed skill's advice
(`docir context`, `docir get`), got a traceback, and reported that it could not
read the design at all — then repeated "docir could not run in the sandbox" as a
finding on every subsequent round.

`docir doctor` cannot warn about it either. It snapshots the environment from
wherever it runs, and outside the sandbox the daemon is up.

## What would fix it

Start the daemon where the executor is *built* rather than on first dispatch, and
on failure build the in-process executor instead, with one warning on stderr.
`_build_executor` is already the one place that chooses between the two
transports, and it is the only place that can fall back: it owns the `Container`
the in-process path has to close, which an executor swallowing its own failure
mid-request could not.

Catch `DaemonError` and `OSError` and nothing wider. A `SchemaError` raised while
the container loads is not a transport failure, and in-process would raise it
again — but silently retrying it as if it were would make the schema error look
like a daemon one.

No caching of the verdict. One process runs one command, and the state that
would have to persist across them belongs in a file the sandbox this exists for
cannot write.

Left out deliberately: skipping the daemon by default under `CI` or a non-tty
stdout, which the report also asks for. That changes the transport for every
scripted caller — a warm daemon is worth most exactly where commands come in
runs — and `DOCIR_NO_DAEMON` already gives a caller that cannot pass a flag the
opt-out.

## Reported

GitHub issue #15, against 0.26.0, by an adopter running docir inside a read-only
agent sandbox.

## Resolution

FIXED 2026-09-18. `start_daemon_executor` starts the daemon where the executor
is built and returns `None` rather than raising when it will not start; the
caller then builds the in-process executor and the command runs, one warning on
stderr naming the reason and `DOCIR_NO_DAEMON=1`. Stdout is untouched, so an
agent parsing it reads the same JSON it would have read.

`DaemonError` and `OSError`, and nothing wider — a `SchemaError` raised while a
container loads is not a transport failure, and swallowing it would report a
broken store as a broken daemon.

**Reproducing it turned up the half that mattered more.** The MCP server built
its own `SocketExecutor` beside the CLI's, so a CLI-only fix would have left the
crash exactly where an adopter meets it: an MCP client spawns the server into
its own environment, which is the sandbox. The start-and-fall-back is one
function now, in `socket_executor`, called by both entry points — the rule
adr-354a4270ecd8 exists to keep, and the same drift that let two CLI flags reach
no MCP tool in 0.18.0.

Exercised against this repository's own corpus with the daemon log replaced by a
directory, which is the reported failure's shape: `docir context` warned and
answered with real ranking and graph expansion, and the MCP server, driven over
stdio by a client doing `initialize` / `tools/list` / `tools/call`, did the same
on `docir_context`. With the log restored, neither warns and the daemon serves.

Four injections, each proven to fail its guard: removing the fallback from the
caller, narrowing the catch to `DaemonError` alone (which is the reported
`OSError` case), widening it to `Exception` (which swallows the schema error),
and restoring the MCP server's own `SocketExecutor`.

## The half it left open, closed straight after

`docir doctor` and `docir daemon status` read `settings.socket_path` directly to report it,
so where *no* temporary directory is usable at all — the reporter's
`FileNotFoundError: No usable temporary directory` — the two commands somebody runs to
diagnose the first failure still ended in a traceback. [[issue-b9800d8265f6]] closed that:
the path reads as absent rather than raising, `daemon status` says "cannot run here" instead
of "not running", and `doctor` reports `no-daemon-socket` as a warning.

`fastembed` was the third layer and went with [[adr-78090be868ec]] — it raised computing its
own cache directory, so reads failed inside the library before docir ran. The model lives in
`~/.docir/models` now. All of `query`, `get`, `search` and `context` answer with no
temporary directory at all.

Left undone on purpose: skipping the daemon by default under `CI` or a non-tty stdout, which
the report asks for as its second point. That changes the transport for every scripted
caller — a warm daemon is worth most exactly where commands come in runs — and
`DOCIR_NO_DAEMON` already gives a caller that cannot pass a flag the opt-out. Its third point
was already true.
