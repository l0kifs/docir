---
archived: true
created: '2026-07-30'
description: Every `unstated` rule here lives in one person's head and in git history.
id: issue-b928ad676595
owner: maintainer
related:
- ref-32cb4f874fbe
- ref-9e4cce368b80
status: open
tags:
- cosmetic
- docs
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

## Disposition

ARCHIVED 2026-07-30, not fixed. The finding is a true statement about a single-maintainer project, so closing it would mean changing the project rather than the code — `CODEOWNERS` names a reviewer, it does not produce one. It is archived rather than resolved because nothing was resolved: 38 of the 47 rules in the register (ref-32cb4f874fbe) are still `assumed`, meaning reconstructed from the code and never confirmed by anyone who could say what was intended. That gap is real and stays open in substance. Archiving keeps it out of the live backlog while leaving it discoverable with `--include-inactive`, so a future reader cannot mistake those 38 rules for ratified ones. The one sub-part with code behind it — the 5 `disputed` rules — was left for a separate pass.
