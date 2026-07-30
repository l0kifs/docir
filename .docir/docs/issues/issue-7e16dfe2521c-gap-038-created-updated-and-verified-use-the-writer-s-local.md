---
created: '2026-07-30'
description: Two teammates in different timezones can stamp different dates for the
  same moment; staleness can differ by a day.
id: issue-7e16dfe2521c
owner: maintainer
related:
- arch-3e305bc76ff0
status: resolved
tags:
- cli
- cosmetic
title: GAP-038 — `created`, `updated` and `verified` use the writer's local date with
  no timezone…
type: issue
updated: '2026-07-30'
---

# GAP-038 — `created`, `updated` and `verified` use the writer's local date with no timezone…

**Class:** unstated · **Severity:** cosmetic · **Confidence:** observed
**Flow:** FLOW-001 · **Step:** date stamping
**Question:** None · **Frequency:** n/a

## Finding

`created`, `updated` and `verified` use the writer's local date with no timezone recorded, and staleness is computed in whole local days.

## What happens today

SystemClock.today() returns `date.today()` — local.

## Impact

Two teammates in different timezones can stamp different dates for the same moment; staleness can differ by a day. Immaterial at a 365-day cadence.

## Proposed default

Accept as-is; record the choice so it is not rediscovered as a bug.

## Resolution

FIXED 2026-07-29 properly, at the maintainer's direction: `SystemClock.today()` returns the UTC calendar date rather than the local one. No migration mechanism — the project has no users yet, so existing dates are not worth a compatibility path. The original entry proposed accepting the skew as immaterial at a 365-day cadence, which was true of the *staleness* consequence and missed the other one: these dates are written into committed files and read by other people, so two teammates either side of midnight stamped different dates for the same moment. That is a correctness problem in shared data, not a rounding problem in a heuristic. Pinned by a test asserting against a UTC date computed in the test rather than against `date.today()`, which is the local value the fix moved away from.

## Actors affected

- repository maintainer

## Evidence

- `src/docir/platform/clock/system.py`

---

Migrated from the discovery gap register (GAP-038); the register itself now lives in this store.
