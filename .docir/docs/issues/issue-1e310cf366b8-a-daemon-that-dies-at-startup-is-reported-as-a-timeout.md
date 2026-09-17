---
code:
- src/docir/entry_points/daemon/lifecycle.py
- src/docir/entry_points/daemon/socket_executor.py
- src/docir/platform/transport/client.py
code_baseline:
  src/docir/entry_points/daemon/lifecycle.py: 584a75aa7d42
  src/docir/entry_points/daemon/socket_executor.py: 5ad7704f083a
  src/docir/platform/transport/client.py: 5fca48050e14
created: '2026-09-16'
description: The client spawns a daemon, waits, and reports the wait — so a store
  whose schema will not load reaches the caller as a timeout instead of the reason,
  which stays in daemon.log.
id: issue-1e310cf366b8
owner: maintainer
related:
- issue-2f07f83e6b84
- adr-56d29d521620
status: resolved
tags:
- cli
- integrity
title: A daemon that dies at startup is reported as a timeout
type: issue
updated: '2026-09-17'
---

A store whose schema will not load takes the daemon down at startup. The client cannot see
that: it spawns one, waits, and reports the wait. The sentence the error was written to carry
— which key is wrong, which docir version the store needs — is in `daemon.log` and nowhere the
caller looks.

## Measured

With the daemon enabled, which is the default:

```
DOCIR_HOME=<store whose schema will not load> python -m docir mcp serve
# instructions: the ordinary ones — the server never read the schema
# docir_query -> ToolError: daemon failed to become ready in time
```

Only `docir --no-daemon` answers the same store instantly and correctly, because that mode
builds the container — and so resolves the schema — in process. In the default mode the CLI
is a socket client that loads no schema: it spawns the daemon and waits out the same
ten-second deadline the MCP server does, and since the fix it too quotes what the daemon
wrote.

## Not the same defect as [[issue-2f07f83e6b84]]

That one killed the MCP server outright, in process, and is fixed: the surface comes up and
every tool returns the reason. This one does not kill anything. The server is healthy, the
daemon is the thing that died, and the failure it produces is a **timeout with the wrong
cause** rather than silence.

They share a symptom — the reader never gets the sentence — and nothing else. The fix for the
first was to keep a message that already existed; the fix for this one is to carry a message
across a process boundary that currently has nowhere to put it.

## What closing it needs

A daemon that can say why it died rather than by being absent.

The cheap version: when a spawn times out, the client quotes the tail of `daemon.log`. It is
honest, it needs no protocol change, and it reports a wrong cause as *one candidate* rather
than as the answer.

The honest version distinguishes "not ready yet" from "will never be ready" at the point the
client is waiting — a change to the pair of timeouts [[adr-56d29d521620]] keeps deliberately
separate, so it costs a decision rather than a patch.

## What shipped

`ensure_running` records the log's size before it spawns, and on a timeout quotes what the
daemon wrote after that point — six lines, pointer rows dropped, capped. A traceback's last
line is the exception, so the sentence naming the cause is what survives the window.

Reading from the recorded offset is the whole of the care: the log is appended to across every
spawn a store has ever done, so quoting its tail unconditionally would attribute last week's
traceback to this morning's timeout — a wrong cause stated with confidence, which is worse
than the bare wait it replaces.

Silence gets its own sentence. A daemon that wrote nothing did not get as far as failing out
loud, which points at the spawn rather than at the store, and the message says so and names
the log.

Quoted as *what it said*, never as the cause: a healthy daemon can miss this deadline too, on
a cold model load, and then those lines are progress. The reader is the one who can tell, and
now has something to tell it from.

The other half of [[adr-56d29d521620]] is untouched. This is the spawn-and-wait path only —
the reply timeout still bounds silence rather than work, and the two still raise different
exceptions.
