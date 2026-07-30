---
created: '2026-07-30'
description: Contradicts a documented invariant.
id: issue-389dc5dac58a
owner: maintainer
related:
- arch-3e305bc76ff0
- ref-1509d5dbb4c3
status: resolved
tags:
- integrity
- blocking
title: GAP-009 — With `--no-daemon`, concurrent `add` invocations all receive the
  same id
type: issue
updated: '2026-07-30'
---

# GAP-009 — With `--no-daemon`, concurrent `add` invocations all receive the same id

**Class:** incorrect · **Severity:** blocking · **Confidence:** observed
**Flow:** FLOW-001 · **Step:** id allocation under concurrency
**Question:** Q-002 · **Frequency:** unknown; requires two agents/processes writing at once, which is the stated multi-agent use case

## Finding

With `--no-daemon`, concurrent `add` invocations all receive the same id. The read-modify-write of the counter is not serialized at the SQLite level; nothing detects the collision.

## What happens today

OBSERVED. Six simultaneous `docir --no-daemon add` calls against one store ALL returned `adr-0002`, all exited 0, and produced six files claiming that id. Only one is visible in the index. The same race with the daemon (the default) produced adr-0002..adr-0007 correctly — the daemon's single-connection loop is what actually serializes.

## Impact

Contradicts a documented invariant. CLAUDE.md states the counter "is what keeps parallel agents from minting the same id"; it is the daemon that does. `--no-daemon` is presented as an equal alternative (README:136-139) and is what the project's own test suite and CI use, so the mode where the guarantee fails is the mode most likely to be scripted.

## Proposed default

Take the counter update inside an IMMEDIATE transaction (or `UPDATE … RETURNING` under a write lock), so allocation is atomic regardless of daemon mode. Failing that, document plainly that `--no-daemon` is single-writer-only and make the bundled profiles use `id_style: random`, which is already implemented and immune (as of 2026-07-26 this is what `docir init` writes by default — see BR-074).

## Resolution

FIXED 2026-07-26. `next_number` is now a single atomic upsert (`INSERT … ON CONFLICT DO UPDATE SET next_value = next_value + 1 RETURNING next_value - 1`), so the increment happens under SQLite's write lock instead of in Python between two statements. `busy_timeout` is now set explicitly in `create_index_engine` so a blocked writer waits rather than erroring. Verified by isolating the change: with the retry loop and file guard temporarily removed, 16 barrier-synchronised concurrent adds x3 rounds produced 16 unique ids every time, where the old code collided at 6. Pinned by tests/modules/documents/test_concurrent_ids.py (marked `slow`, spawns real processes), which was confirmed to FAIL against the reverted implementation. Note the guarantee no longer depends on the daemon; the daemon remains the serializer for everything else.

## Actors affected

- AI coding agent
- repository maintainer
- CI job

## Evidence

- `src/docir/platform/persistence/repositories.py:48-56`
- `src/docir/platform/transport/server.py:20-25`
- `src/docir/modules/documents/application/services/id_generator.py:3-5`
- `ref-1509d5dbb4c3 (discovery probe log)`

---

Migrated from the discovery gap register (GAP-009); the register itself now lives in this store.
