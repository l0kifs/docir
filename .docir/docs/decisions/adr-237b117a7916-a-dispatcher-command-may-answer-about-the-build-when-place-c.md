---
code:
- src/docir/entry_points/dispatch.py
- src/docir/modules/release/domain/deprecations.py
code_baseline:
  src/docir/entry_points/dispatch.py: 282abcf40e30
  src/docir/modules/release/domain/deprecations.py: 79544413bab0
created: '2026-09-17'
description: Why the deprecation register is a command and a tool, what test lets
  it be one when the rest of doctor is not, and why it is not folded into store_status.
id: adr-237b117a7916
owner: maintainer
related:
- kind: refines
  to: adr-354a4270ecd8
- adr-6d4d43d44075
- adr-909734bced92
- issue-8b227c299e63
status: accepted
tags:
- cli
- architecture
title: A dispatcher command may answer about the build, when place cannot change the
  answer
type: decision
updated: '2026-09-22'
verified: '2026-09-22'
verified_code:
  src/docir/entry_points/dispatch.py: 282abcf40e30
  src/docir/modules/release/domain/deprecations.py: 79544413bab0
verified_content: ff5bd568596f
---

The dispatcher's commands have all been about a store: its documents, its tags, its index.
`deprecations` is about the docir running them. It is allowed, on a property the rest of
`docir doctor` does not have, and the property is the rule.

## What forced the question

[[adr-6d4d43d44075]] put the dated register in `docir doctor`, and [[adr-354a4270ecd8]] makes
every MCP tool one `Request` through the dispatcher — one tool per command, never a second
implementation. There is no `doctor` command, so there was no tool, so the reader those dates
were written for could not read them ([[issue-8b227c299e63]]).

Adding a tool without a command would have been the quick way and the wrong one: two
implementations of one answer is exactly what that rule exists to stop.

## The rule: a command may answer about the build when the answer does not depend on where it runs

[[adr-909734bced92]] kept `doctor` out of the dispatcher for a good reason — most of what it
reports is about the *client process*: which store the working directory resolved to, whether
a stale `DOCIR_EMBEDDER` is set, whether the daemon on this machine is serving current code.
The MCP server runs in the daemon, so those answers would be about the wrong process.

The register is not like that. It is a constant in the installed package plus today's date,
and it reads the same in the daemon as in the shell. That is the whole test, and it is narrow
on purpose: a command passes it only when running somewhere else cannot change the answer.

## Why not fold it into `store_status`

That tool already answers whether this store's index is current, and it gained the store
format numbers because those describe a store. Adding the register would have been quicker and
would have made one tool about two subjects — a store, and the build reading it — which is the
question a reader then has to disentangle every time.

Its own command says which subject it is, and the name says it before the payload does.

## What it costs

A second place that reads the register — `doctor` builds its `compat` section directly,
because it must answer while the store is unopenable, and a dispatcher command cannot. They
are not two implementations: both call `describe_deprecations`, which shapes the payload once.
The split is between *transports*, not between answers.

`Dispatcher` also gains a clock, which it had no reason for before. That is honest rather than
incidental: "has this date passed" is a question about today, and every other clock in docir is
injected so a test can stand on the far side of a sunset without waiting for it.

## What it does not become

A place for the rest of `doctor`. The environment half stays out, and the test is unchanged:
if running in the daemon rather than the shell can change the answer, it is not a command.
