---
created: '2026-07-30'
description: The registry can only grow.
id: issue-498cbbaeac2f
owner: maintainer
related:
- arch-ccfcceeb35eb
status: resolved
tags:
- tags
- cosmetic
title: GAP-029 — No usage counts, so dead tags are invisible
type: issue
updated: '2026-07-30'
---

# GAP-029 — No usage counts, so dead tags are invisible

**Class:** missing · **Severity:** cosmetic · **Confidence:** observed
**Flow:** FLOW-005 · **Step:** tag list
**Question:** None · **Frequency:** n/a

## Finding

No usage counts, so dead tags are invisible.

## What happens today

tag_service.py:54-60 returns key + description only.

## Impact

The registry can only grow.

## Proposed default

Include a document count per tag.

## Actors affected

- repository maintainer

## Evidence

- `src/docir/modules/tags/application/services/tag_service.py:54-60`

---

Migrated from the discovery gap register (GAP-029); the register itself now lives in this store.

## Resolution

FIXED 2026-07-30. `docir tag list` now reports a `usage` count per tag: the number of indexed documents carrying it, archived included. Archived documents count because that is the set `tag rm` refuses to remove over — a tag reported as dead that then needs `--force` would be worse than no count. Zero survives JSON trimming (`_trim` never drops a numeric zero), because zero is the finding. `TagRepository.usage_counts(keys)` fetches counts for the page's keys only, so listing costs one extra query per page rather than one per tag; `usage` lives on `TagView` rather than the `Tag` entity, since how many documents carry a tag is a fact about the corpus, not about the tag. Verified by injecting the bug: with the count hard-coded to 0, four of the six new guards fail. Against docir's own registry, no tag is dead — the lowest are `daemon` and `release` at 1 each.
