---
created: '2026-07-30'
description: A bulk mutation reports as a single-key operation.
id: issue-d69a47904478
owner: maintainer
related:
- arch-ccfcceeb35eb
status: resolved
tags:
- cli
- cosmetic
title: GAP-030 — Reports only `removed <key>`; never says how many documents it rewrote
type: issue
updated: '2026-07-30'
---

# GAP-030 — Reports only `removed <key>`; never says how many documents it rewrote

**Class:** unstated · **Severity:** cosmetic · **Confidence:** observed
**Flow:** FLOW-005 · **Step:** tag rm --force
**Question:** None · **Frequency:** every forced tag removal

## Finding

Reports only `removed <key>`; never says how many documents it rewrote.

## What happens today

dispatch.py:159-161 returns `{removed: key}`.

## Impact

A bulk mutation reports as a single-key operation.

## Proposed default

Return the affected document ids.

## Resolution

FIXED 2026-07-29. `TagService.remove` returns the ids it stripped the tag from; the wire response carries `documents` and the CLI says "stripped it from N document(s)". Cheap, but the reason it mattered changed this cycle rather than the finding: `delete --force` (GAP-007) and `tag rename --merge` (GAP-028) both now name what they rewrote, so a forced removal staying silent was the odd one out among three commands that rewrite other people's files.

## Actors affected

- repository maintainer

## Evidence

- `src/docir/entry_points/dispatch.py:159-161`

---

Migrated from the discovery gap register (GAP-030); the register itself now lives in this store.
