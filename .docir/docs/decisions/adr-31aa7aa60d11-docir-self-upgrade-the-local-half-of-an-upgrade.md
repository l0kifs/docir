---
code:
- src/docir/entry_points/cli/app.py
- src/docir/entry_points/composition.py
- src/docir/platform/persistence/alembic/versions/**
created: '2026-08-09'
description: One command for the steps that follow a new docir release, and why installing
  the new docir is not one of them.
id: adr-31aa7aa60d11
owner: maintainer
related:
- adr-bd3a820cc57a
- adr-3a2d5ee7bc84
- adr-927aa43d9635
status: accepted
tags:
- cli
- agents
- schema
title: 'docir self upgrade: the local half of an upgrade'
type: decision
updated: '2026-08-09'
---

## Context

An upgrade left three things for the user to do, in order, and nothing told them
so: rebuild the index (derived, gitignored, and the only place the schema
baseline and — now — the build version are recorded), refresh the generated agent
instruction files (rendered from a template inside the package, stamped with the
version that rendered them), and read what `check` says afterwards. The
procedure existed only in one release's "Upgrade notes". docir 0.11.0 shipped
with its own skill file still claiming v0.10.0, which is what the omission looks
like in practice.

## Decision

**`docir self upgrade` runs the three local steps, in that order.** `check` goes
last, so its findings describe the state the upgrade left rather than the one it
started from.

**A `self` group, not a top-level verb.** `docir update <id>` already means
"edit a document", and a bare `docir upgrade` sits one typo away from it in a
tool whose primary noun is a document. `uv` draws the same line with `uv self
update` versus `uv tool upgrade`: `self` is the tool acting on its own
installation and what it generated. The name is chosen to survive the package
half landing under it — renaming a command breaks every saved agent prompt that
names it.

**It does not install a new docir.** The process is running the code that would
be replaced, so everything after that call is still the old build's work —
including the rebuild that stamps which version built the index, which would
then record the version that is on its way out. Doing it properly means
detecting how docir was installed (uv tool, pipx, pip, a `uv sync` workspace,
uvx — a wrong guess "upgrades" a checkout) and re-execing the new binary to
finish. That is a separate decision; until it is made, the command says what to
run and refuses to guess.

**The index records which docir built it, in its own one-row table.** Not in the
schema baseline: that payload is diffed line by line and printed to the user, so
a version key inside it would render every upgrade as a schema change. And the
baseline cannot answer this question anyway — it compares *schemas*, so it is
silent for a release that changes how documents are read rather than what they
must contain. Chunked embeddings (adr-927aa43d9635) rewrote every vector in the
index without touching a type, a status or a cadence.

`reindex` is the only writer, for the reason it is the only writer of the
baseline: it is already the "make derived state agree with its sources" command,
and a separate acknowledgement verb would be a ritual whose only effect is to
silence a report.

**The finding is `stale-index-build`, a warning, on inequality.** Not "older
than": a downgrade needs the same rebuild, and ordering two version strings is a
question this does not have to answer to give the right advice. A warning
because every store is in this state between an upgrade and the next rebuild —
an error kind would red-light every repository on release day, which is the
argument adr-bd3a820cc57a makes about schema drift, one step stronger: here not
even the rules have changed.

**Absent means unknown.** A store that has not been rebuilt since the table
arrived reports nothing, rather than reporting itself as stale once, for
something no one can act on differently.

**Not an MCP tool.** The two halves it orchestrates (`reindex`, `check`) are
already exposed, and an agent that wants them can call them. The composite is
CLI-only because the package half is meant to land inside it, and at that point
the command replaces the binary of the very server the client is talking to.

## Consequences

- One command to run after an upgrade, and a finding that asks for it by name.
- `MaintenanceService` takes the running version — the composition root passes
  `__version__`, as it already does for the agent-instruction service.
- The orchestration lives in the composition root beside `initialize_store`,
  not in a module: it spans `documents` (through the executor) and `agents` (in
  process), and that spanning is exactly what wiring is for.
- The package upgrade remains manual and is named in the output.
