---
created: '2026-07-30'
description: Reasonable design; undocumented, and surprising given tags appear in
  output.
id: issue-a776b08ceaea
owner: maintainer
related:
- arch-ccfcceeb35eb
status: resolved
tags:
- retrieval
- cosmetic
title: Tags are in neither the FTS index nor the embedded text, so `search` cannot
  find them
type: issue
updated: '2026-08-05'
---

**Class:** unstated · **Severity:** cosmetic
**Flow:** arch-ccfcceeb35eb · **Step:** search for a tag name
**Question:** None · **Frequency:** n/a

## Finding

Tags are neither in the FTS index nor in the embedded text, so `docir search auth` does not find documents tagged `auth`.

## What happens today

FTS5 indexes title/description/body (migration 0001:88-92); `embedding_text()` is title+description+body (document.py:40-47).

## Impact

Reasonable design; undocumented, and surprising given tags appear in output.

## Proposed default

State it in the README's search description.

## Resolution

DOCUMENTED 2026-07-29, as proposed — the design stands. Tags are a controlled vocabulary for `query --tag`; folding them into FTS would let one tag match flood out the text matches the query was actually for. The README's command table, a new "Scope and limits" section and the agent guide's read table all now say search covers title/description/body and *not* tags, and point at `query --tag`.

## Actors affected

- AI coding agent

## Evidence

- `src/docir/platform/persistence/alembic/versions/0001_initial_index.py:88-92`
- `src/docir/modules/documents/domain/entities/document.py:40-47`

---

Migrated from the discovery gap register (GAP-031); the register itself now lives in this store.
