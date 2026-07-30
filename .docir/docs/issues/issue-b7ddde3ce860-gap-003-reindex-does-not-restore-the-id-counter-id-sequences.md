---
created: '2026-07-30'
description: Silent loss of a decision record on the documented happy path.
id: issue-b7ddde3ce860
owner: maintainer
related:
- arch-0a3c2d6d54a6
- ref-1509d5dbb4c3
status: resolved
tags:
- integrity
- blocking
title: GAP-003 — `reindex` does not restore the id counter (`id_sequences`), so after
  any rebuild the…
type: issue
updated: '2026-07-30'
---

# GAP-003 — `reindex` does not restore the id counter (`id_sequences`), so after any rebuild the…

**Class:** incorrect · **Severity:** blocking · **Confidence:** observed
**Flow:** FLOW-003 · **Step:** reindex, then the next add
**Question:** Q-001 · **Frequency:** once per fresh clone that then adds a document — i.e. every new contributor

## Finding

`reindex` does not restore the id counter (`id_sequences`), so after any rebuild the next `add` re-issues an id that is already in use. Both files persist; the index keeps only the newer one; the older document becomes invisible to every read path.

## What happens today

OBSERVED end to end. Store with adr-0001 "First" and adr-0002 "Second"; delete index.db (it is gitignored — this is exactly a fresh clone); `docir reindex` reports documents_indexed 2; `docir add --type decision --title "Third"` returns id **adr-0001**. Disk now holds adr-0001-first-decision.md AND adr-0001-third-decision.md. `docir get adr-0001` returns "Third decision". `docir query` lists two documents, not three. "First decision" is unreachable through get, query, search and context while its file sits untouched on disk. No error, no warning, exit code 0.

## Impact

Silent loss of a decision record on the documented happy path. It requires no concurrency, no --force, no unusual input — only `git clone` followed by the rebuild command the README tells you to run. It contradicts the project's first thesis ("the index is a derived, rebuildable projection"): the rebuild is not faithful.

## Proposed default

`_reindex_documents` should, for each sequential-id type, set the counter to max(existing numeric suffix) + 1 as part of the rebuild. Add a regression test that clones→reindexes→adds and asserts the new id is unused.

## Resolution

FIXED 2026-07-26. `MaintenanceService._restore_id_sequences` rebuilds the counter from the ids on disk (monotonic, so deleting the highest-numbered doc does not free its id). Two backstops added for the paths reindex does not cover: `IdGenerator` skips a candidate already indexed, and `add` refuses to write when a file already claims the id (`DuplicateDocumentIdError`, exit 5) instead of silently overwriting. Verified by replaying PROBE-1 against the real CLI — clone→reindex→add now yields adr-0003 and all three documents stay visible. Pinned by test_reindex_restores_the_id_counter, test_reindex_never_rewinds_the_counter and test_add_refuses_to_clobber_a_file_owning_the_allocated_id.

## Actors affected

- AI coding agent
- repository maintainer
- git / branch merge

## Evidence

- `src/docir/modules/documents/application/services/maintenance_service.py:148-174`
- `src/docir/platform/persistence/repositories.py:48-56`
- `ref-1509d5dbb4c3 (discovery probe log)`

---

Migrated from the discovery gap register (GAP-003); the register itself now lives in this store.
