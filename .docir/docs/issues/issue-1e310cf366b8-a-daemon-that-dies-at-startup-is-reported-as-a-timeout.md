---
code:
- src/docir/entry_points/daemon/lifecycle.py
- src/docir/entry_points/daemon/socket_executor.py
code_baseline:
  src/docir/entry_points/daemon/lifecycle.py: 584a75aa7d42
  src/docir/entry_points/daemon/socket_executor.py: 5ad7704f083a
created: '2026-09-16'
description: The client spawns a daemon, waits, and reports the wait — so a store
  whose schema will not load reaches the caller as a timeout instead of the reason,
  which stays in daemon.log.
id: issue-1e310cf366b8
owner: maintainer
related:
- issue-2f07f83e6b84
- adr-56d29d521620
status: open
tags:
- cli
- integrity
title: A daemon that dies at startup is reported as a timeout
type: issue
updated: '2026-09-16'
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

The CLI answers the same store instantly and correctly, because it resolves the schema in
process before it reaches the socket.

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
