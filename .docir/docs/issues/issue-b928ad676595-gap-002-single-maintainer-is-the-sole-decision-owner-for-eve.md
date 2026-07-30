---
created: '2026-07-30'
description: Every `unstated` rule here lives in one person's head and in git history.
id: issue-b928ad676595
owner: maintainer
related:
- ref-9e4cce368b80
status: open
tags:
- docs
- cosmetic
title: GAP-002 — Single maintainer is the sole decision owner for every rule in this
  register
type: issue
updated: '2026-07-30'
---

# GAP-002 — Single maintainer is the sole decision owner for every rule in this register

**Class:** unstated · **Severity:** cosmetic · **Confidence:** observed
**Flow:** None · **Step:** governance
**Question:** None · **Frequency:** n/a

## Finding

Single maintainer is the sole decision owner for every rule in this register.

## What happens today

No CODEOWNERS, no governance doc, no second reviewer.

## Impact

Every `unstated` rule here lives in one person's head and in git history.

## Proposed default

Not actionable as a code change; recorded so the question queue's single audience is understood.

## Actors affected

- repository maintainer

## Evidence

- `LICENSE`
- `git log --format=%an | sort -u`

---

Migrated from the discovery gap register (GAP-002); the register itself now lives in this store.
