---
code:
- src/docir/entry_points/mcp/server.py
- src/docir/modules/release/domain/deprecations.py
code_baseline:
  src/docir/entry_points/mcp/server.py: 2977f215d50c
  src/docir/modules/release/domain/deprecations.py: d5ff6f0936b8
created: '2026-09-16'
description: doctor carries every dated announcement and has no MCP tool, so the agent
  the dates were written for cannot read them.
id: issue-8b227c299e63
owner: maintainer
related:
- adr-6d4d43d44075
- adr-354a4270ecd8
status: resolved
tags:
- cli
- integrity
title: The deprecation register is not askable over MCP
type: issue
updated: '2026-09-17'
---

`docir doctor | jq '.compat'` carries every surface this build will stop accepting and the
date each stops ([[adr-6d4d43d44075]]). Over MCP there is no way to ask. The store-format half
reached `docir_store_status`, because those are facts about a store and that tool already
answers those; the deprecation register did not, because it is a fact about the *build*.

## Why the obvious placement does not work

[[adr-354a4270ecd8]] makes every MCP tool one `Request` through the dispatcher — one tool per
dispatcher command, never a second implementation. There is no `doctor` command there: most
of what `doctor` reports is about the client process, and the MCP server runs in the daemon,
so [[adr-909734bced92]] deliberately left it out.

The register is not like the rest of `doctor`. It reads no environment and no process — it is
a constant in the package plus today's date, and both are as true in the daemon as in the
shell. It is the one part of that report the existing argument does not cover.

## Who it costs

The reader the announcement was written for. An agent driving docir over MCP holds only the
installed package, never opens a changelog, and is exactly the caller that would otherwise
script around a flag due to stop working — which is the whole case [[adr-6d4d43d44075]] makes
for putting a date on it.

## What a fix has to decide

Whether a dispatcher command may answer a question about the build rather than about a store.
Adding `compat` there gives both transports one implementation and settles it; putting the
register in `docir_store_status` instead would answer it faster and quietly make that tool
about two things.

## What shipped

`deprecations` is a dispatcher command, so `docir_deprecations` is one `Request` like every
other tool — the shape [[adr-354a4270ecd8]] requires, rather than a second implementation
beside `doctor`'s. Verified over real stdio against this store: 23 tools listed, the register
returned with its replacement and sunset.

The rule that let a command answer about the *build* rather than a store is
[[adr-237b117a7916]]: it may, when running somewhere else cannot change the answer. The
register is a constant in the package plus today's date, which reads the same in the daemon as
in the shell — unlike the rest of `docir doctor`, which is about the client process and stays
out.

Not folded into `docir_store_status`, which would have been quicker and would have made one
tool about a store and about the build reading it.

`describe_deprecations` shapes the payload once, so `doctor`'s `compat` section and the
command cannot disagree about a field name. `doctor` still reads the register directly rather
than dispatching, because it has to answer while the store is unopenable — a split between
transports, not between answers.
