---
created: '2026-07-30'
description: The registry can only grow.
id: issue-498cbbaeac2f
owner: maintainer
related:
- arch-ccfcceeb35eb
status: open
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
