---
created: '2026-07-30'
description: Fires on the documented happy path with no concurrency, no --force and
  no unusual input. It contradicts the project's first thesis, so the answer also
  decides whether that thesis…
id: issue-88dd653b9f39
owner: maintainer
related:
- issue-61b66ed696de
- issue-b7ddde3ce860
status: resolved
tags:
- integrity
- blocking
title: Q-001 — `reindex` rebuilds documents, tags, FTS and embeddings but not the
  id counter, so on a…
type: issue
updated: '2026-07-30'
---

# Q-001 — `reindex` rebuilds documents, tags, FTS and embeddings but not the id counter, so on a…

**Gap:** GAP-003 · **Also resolves:** GAP-013 · **Audience:** repo maintainer
**Blocking:** yes · **Rank:** 1 · **Asked:** 2026-07-26 · **Answered:** 2026-07-26
**Authority:** repo maintainer (instructed the fix directly)

## Question

`reindex` rebuilds documents, tags, FTS and embeddings but not the id counter, so on a fresh clone the next `add` re-issues a live id and the older document disappears from every read path. Is the id counter meant to be part of the derived, rebuildable index (in which case reindex must reconstruct it from the files), or is it authoritative state that must never be lost (in which case it cannot be gitignored)?

## What the system does today

OBSERVED: clone (index absent, it is gitignored) → `docir reindex` → `docir add` returns an id that is already in use. Two files claim it; the index keeps the newer; the older document is unreachable via get/query/search/context though its file is untouched. Exit code 0 throughout. Evidence: maintenance_service.py:148-174, repositories.py:48-56.

## Proposed answer

Derived. `_reindex_documents` should set each sequential prefix's counter to max(numeric suffix seen) + 1 as part of the rebuild, with a regression test for clone→reindex→add.

## Why it matters

Fires on the documented happy path with no concurrency, no --force and no unusual input. It contradicts the project's first thesis, so the answer also decides whether that thesis needs qualifying in the README.

## Answer

Derived — the proposed answer was adopted. reindex now restores the counter, with two allocation-time backstops. See GAP-003 resolution.

---

Migrated from the discovery question queue (Q-001); the queue itself now lives in this store.
