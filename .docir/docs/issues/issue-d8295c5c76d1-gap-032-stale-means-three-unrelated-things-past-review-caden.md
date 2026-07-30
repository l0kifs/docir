---
created: '2026-07-30'
description: Maintenance hazard only; no user-visible defect.
id: issue-d8295c5c76d1
owner: maintainer
related:
- adr-bd7c4f3c5764
status: resolved
tags:
- staleness
- cosmetic
title: GAP-032 — `stale` means three unrelated things — past review cadence, changed
  on disk, and…
type: issue
updated: '2026-07-30'
---

# GAP-032 — `stale` means three unrelated things — past review cadence, changed on disk, and…

**Class:** misleading · **Severity:** cosmetic · **Confidence:** observed
**Flow:** None · **Step:** reading the code
**Question:** None · **Frequency:** n/a

## Finding

`stale` means three unrelated things — past review cadence, changed on disk, and orphaned index row — two of them within eleven lines of one method.

## What happens today

See 04-glossary.yaml, term `stale`.

## Impact

Maintenance hazard only; no user-visible defect. Sense (1) is the product feature and should keep the word.

## Proposed default

Rename sense 2 to `changed_on_disk` and sense 3 to `orphaned`.

## Resolution

FIXED 2026-07-29, and two-thirds of it incidentally. Sense (2), "changed on disk", became `disk_diverged` while stating GAP-037; sense (3), the orphaned index row, is now `orphaned` in the removal sweep. Sense (1) keeps the word, as proposed — it is the product feature.

## Actors affected

- repository maintainer

## Evidence

- `src/docir/modules/documents/application/services/document_service.py:136`
- `src/docir/modules/documents/application/services/document_service.py:288-295`
- `src/docir/modules/documents/application/services/maintenance_service.py:168`

---

Migrated from the discovery gap register (GAP-032); the register itself now lives in this store.
