---
code:
- src/docir/entry_points/doctor.py
- src/docir/entry_points/mcp/server.py
code_baseline:
  src/docir/entry_points/doctor.py: e81d399f8223
  src/docir/entry_points/mcp/server.py: 6f7af9225b96
created: '2026-09-23'
description: Why docir_doctor is the second exception to one-tool-per-dispatcher-command,
  and why the composition and payload moved out of the CLI to get there.
id: adr-a18d0577739f
owner: maintainer
related:
- issue-e9ef984d5ec7
- kind: refines
  to: adr-354a4270ecd8
status: proposed
tags: []
title: The environment an MCP client runs in is a tool, because it is not a command
type: decision
updated: '2026-09-23'
---

## Decision

`docir_doctor` joins `docir_schema` as an MCP tool with no dispatcher command behind it. The
report's composition and its payload shape move from the CLI into `entry_points/doctor.py`, and
both transports call them.

## Why it cannot be a command

Every other tool is one `Request` through a `RequestExecutor`, which is what makes the CLI and
MCP unable to answer differently ([[adr-354a4270ecd8]]). `doctor` cannot join them, and not for
want of trying: it snapshots the environment **before** anything dispatches, because dispatching
is what replaces a daemon serving other code and builds a missing index. Both facts are gone by
the time a first reply returns.

So a `doctor` command would report the state *after* the repairs it exists to tell you about.
The ordering is the feature.

## Why it is a tool anyway

An MCP-only agent could see none of its own environment: not the daemon, not the peers a
federated read was silently skipping, not the embedding model actually in force, not the thread
cap [[issue-e9ef984d5ec7]]. `docir_store_status` covers the store half and is deliberately
"facts only the index can answer" — an environment fact does not belong in it.

The same argument `docir_schema` was excepted on: a thing an agent needs that is not a command.
The test asserting the tool surface names both by hand, so a third stays a decision.

## What moved, and why that is the point

A second transport composing the report itself is the drift the one-implementation rule exists
to prevent, and it would be invisible — two reports that merely disagree.

So `build_report` (snapshot, then store, then findings, in that order) and `as_payload` (the
section shape) live in `doctor.py`, with `store_reply`'s coercion beside them because both
transports have to read an unanswerable store the same way. The CLI keeps only what is its
own: the spinner, and the choice between a table and JSON.

The store half still goes through the executor, so the report describes the daemon actually
answering rather than a second container built beside it.

## It answers when nothing else does

The composition root supplies `diagnose` on the store-unreadable path too. Explaining why a
store will not open is what doctor is *for*, so it is the one tool that must keep working when
every other one returns the refusal — the surface [[issue-2f07f83e6b84]] kept alive, now with
something useful to say.

## Consequences

An agent on either transport can answer "is this installation healthy, and what is it running
with" in one call. What no tool can do is *change* it: the variables the report names are read
where the server was launched, so the agent tells the person what to export.
