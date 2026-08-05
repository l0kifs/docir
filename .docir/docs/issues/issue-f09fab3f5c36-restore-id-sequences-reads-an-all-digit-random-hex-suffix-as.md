---
created: '2026-07-30'
description: Latent only.
id: issue-f09fab3f5c36
owner: maintainer
related:
- arch-0a3c2d6d54a6
- issue-b7ddde3ce860
status: resolved
tags:
- integrity
- cosmetic
title: '`_restore_id_sequences` reads an all-digit random hex suffix as a sequential
  number'
type: issue
updated: '2026-08-05'
---

**Class:** incorrect · **Severity:** cosmetic
**Flow:** arch-0a3c2d6d54a6 · **Step:** reindex over a store using random ids
**Question:** None · **Frequency:** 0.36% of random ids; consequence requires a later switch to sequential

## Finding

`_restore_id_sequences` classifies an id as sequential by testing whether its suffix is all digits, but a 12-char random hex token is all digits roughly once in 281 ids. Such an id is then read as the number 12345678901 and the prefix's counter is raised above it.

## What happens today

FOUND 2026-07-26 by reasoning about the interaction of two same-day changes (the issue-b7ddde3ce860 counter restore, and `docir init` defaulting to `id_style: random`). Verified arithmetically: P(all digits) = (10/16)^12 = 0.36%; `DocId("adr-012345678901").number` returns 12345678901. Harmless while the type stays `random` — nothing reads the counter — so there is no user-visible symptom today.

## Impact

Latent only. It surfaces if a type is later switched from `random` to `sequential`: the next id is then an eleven-digit number (`adr-12345678902`) rather than `adr-0001`. No data loss, no collision — the ids are still unique and still valid.

## Proposed default

Restore counters only for prefixes whose type declares `sequential`. `MaintenanceService` already holds the schema, so it can build that prefix set and skip the rest — the digit-shape test is the wrong signal for the question being asked.

## Resolution

FIXED 2026-07-26. `_restore_id_sequences` now derives the set of prefixes whose type declares `sequential` from the schema and considers only those; it returns immediately when a store has none. A second guard, `DocId.looks_random`, skips a suffix of random-token length even under a sequential prefix, which covers the leftovers of a type switched from `random` to `sequential` (length disambiguates: a counter would need a hundred billion documents to reach twelve digits). Pinned by test_reindex_ignores_random_ids_when_restoring_the_counter, confirmed to FAIL with `assert 'adr-12345678902' == 'adr-0001'` against the unguarded version, and by test_reindex_still_restores_the_counter_for_sequential_types, which holds the issue-b7ddde3ce860 fix in place.

## Actors affected

- repository maintainer

## Evidence

- `src/docir/modules/documents/application/services/maintenance_service.py:136-157`
- `src/docir/modules/documents/domain/value_objects/identifiers.py:64-73`

---

Migrated from the discovery gap register (GAP-041); the register itself now lives in this store.
