---
created: '2026-07-30'
description: One field is wrong on one rarely-hit path.
id: issue-7d4fdccf8343
owner: maintainer
related:
- adr-bd7c4f3c5764
- arch-3e305bc76ff0
status: resolved
tags:
- staleness
- cosmetic
title: GAP-015 — The no-op early return builds the view without computing staleness,
  so a stale document…
type: issue
updated: '2026-07-30'
---

# GAP-015 — The no-op early return builds the view without computing staleness, so a stale document…

**Class:** misleading · **Severity:** cosmetic · **Confidence:** observed
**Flow:** FLOW-001 · **Step:** archive/unarchive on a document already in that state
**Question:** None · **Frequency:** archiving an already-archived document

## Finding

The no-op early return builds the view without computing staleness, so a stale document reports `stale: false`.

## What happens today

document_service.py:166 and :180 call `from_document(document)` with no `stale=` argument; the dataclass default is False (dto.py:50).

## Impact

One field is wrong on one rarely-hit path.

## Proposed default

Pass `stale=self._is_stale(document)` on both early returns.

## Resolution

FIXED 2026-07-29. Both no-op early returns now pass `stale=self._is_stale(document)`. RE-CLASSIFIED on the way: filed `cosmetic` ("one field is wrong on one rarely-hit path"), but it put a *wrong value in the machine contract* — `get` reported `stale: true` for a document `unarchive` reported as fresh, and `stale` exists to be trusted. Cheap to fix and not cosmetic; the label was fair when filed and stopped being fair once the product leaned on machine-readable output. NOTE, found while writing the test: `archive`/`unarchive` stamp `updated`, so archiving a stale document makes it fresh. That is defensible — archiving is a human decision about the document, like a status change, not a mechanical rewrite — but it means the first attempt at this test proved nothing. Recorded so the next reader does not repeat it.

## Actors affected

- AI coding agent

## Evidence

- `src/docir/modules/documents/application/services/document_service.py:166`
- `180`
- `src/docir/modules/documents/application/dto.py:50`

---

Migrated from the discovery gap register (GAP-015); the register itself now lives in this store.
