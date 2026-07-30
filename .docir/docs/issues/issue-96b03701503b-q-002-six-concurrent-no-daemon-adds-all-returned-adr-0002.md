---
created: '2026-07-30'
description: '"Parallel agents" is the exact scenario the invariant claims to protect,
  and `--no-daemon` is the mode most likely to appear in scripts and CI.'
id: issue-96b03701503b
owner: maintainer
related:
- issue-389dc5dac58a
status: resolved
tags:
- integrity
- blocking
title: Q-002 — Six concurrent `--no-daemon` adds all returned `adr-0002`
type: issue
updated: '2026-07-30'
---

# Q-002 — Six concurrent `--no-daemon` adds all returned `adr-0002`

**Gap:** GAP-009 · **Also resolves:** — · **Audience:** repo maintainer
**Blocking:** yes · **Rank:** 2 · **Asked:** 2026-07-26 · **Answered:** 2026-07-26
**Authority:** repo maintainer (instructed the fix directly)

## Question

Six concurrent `--no-daemon` adds all returned `adr-0002`. With the daemon they were correctly unique. Is `--no-daemon` intended to be safe for parallel agents — or is the daemon a hard requirement for concurrent writing, and the counter's role in CLAUDE.md overstated?

## What the system does today

OBSERVED: 6 simultaneous `docir --no-daemon add` → six files claiming adr-0002, all exit 0, five documents invisible. Same race with the daemon → adr-0002..adr-0007. CLAUDE.md attributes collision-freedom to the SequenceRow counter; the actual mechanism is the daemon's single-connection server loop (transport/server.py:20-25). The project's own test suite and CI force DOCIR_NO_DAEMON.

## Proposed answer

Make allocation atomic regardless of mode (counter update inside an IMMEDIATE transaction, or `UPDATE … RETURNING` under a write lock). `id_style: random` already exists and is immune, but no shipped profile uses it.

## Why it matters

"Parallel agents" is the exact scenario the invariant claims to protect, and `--no-daemon` is the mode most likely to appear in scripts and CI.

## Answer

ANSWERED 2026-07-26 by implementation: allocation is now atomic in both modes via a single upsert statement. `--no-daemon` is safe for parallel writers. CLAUDE.md updated to state why the invariant holds. See GAP-009 resolution.

---

Migrated from the discovery question queue (Q-002); the queue itself now lives in this store.
