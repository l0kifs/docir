---
created: '2026-07-30'
description: A third route to a duplicate id, and the sharpest one.
id: issue-61b66ed696de
owner: maintainer
related:
- adr-d3e3616400bf
- arch-3e305bc76ff0
status: resolved
tags:
- persistence
- material
title: GAP-013 — The markdown file is written before the transaction commits, so an
  interruption in…
type: issue
updated: '2026-07-30'
---

# GAP-013 — The markdown file is written before the transaction commits, so an interruption in…

**Class:** unstated · **Severity:** material · **Confidence:** observed
**Flow:** FLOW-001 · **Step:** between the file write and the index commit
**Question:** Q-001 · **Frequency:** unknown; requires a crash or kill mid-write

## Finding

The markdown file is written before the transaction commits, so an interruption in between leaves a file on disk that the index does not know about.

## What happens today

document_service.py:118-123 — write, then save/index/mark, then commit. No test covers the interruption; `reindex` would repair it if anyone knew to run it.

## Impact

A third route to a duplicate id, and the sharpest one. `next_number` only *flushes* inside the transaction (repositories.py:55), so an interruption before the commit rolls the counter back while the file it already wrote survives on disk. The next `add` therefore issues that same id again. Since the file is canonical the document is not lost — the correct trade-off — but the atomicity boundary is documented as covering "file, metadata, FTS, relations" (CLAUDE.md) and in fact covers only the last three.

## Proposed default

Write the file after the commit (accepting a lost file over a duplicated id), or have `check` flag files present on disk but absent from the index. Either way, state the real boundary in CLAUDE.md.

## Resolution

MITIGATED 2026-07-26 by the same change as GAP-003: a crash between the file write and the commit still leaves an unindexed file, but the next `add` no longer silently overwrites it — the create is refused with DuplicateDocumentIdError pointing at `docir reindex`. The underlying ordering (file written before commit) is unchanged and still undocumented.

## Actors affected

- repository maintainer
- AI coding agent

## Evidence

- `src/docir/modules/documents/application/services/document_service.py:118-123`

---

Migrated from the discovery gap register (GAP-013); the register itself now lives in this store.
