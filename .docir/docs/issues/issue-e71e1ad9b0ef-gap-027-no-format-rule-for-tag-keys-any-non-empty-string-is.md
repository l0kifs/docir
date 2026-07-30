---
created: '2026-07-30'
description: Two agents will produce `auth`, `Auth` and `authentication` and nothing
  objects.
id: issue-e71e1ad9b0ef
owner: maintainer
related:
- arch-ccfcceeb35eb
status: open
tags:
- tags
- cosmetic
title: GAP-027 — No format rule for tag keys — any non-empty string is accepted
type: issue
updated: '2026-07-30'
---

# GAP-027 — No format rule for tag keys — any non-empty string is accepted

**Class:** missing · **Severity:** cosmetic · **Confidence:** observed
**Flow:** FLOW-005 · **Step:** tag add
**Question:** None · **Frequency:** unknown

## Finding

No format rule for tag keys — any non-empty string is accepted.

## What happens today

No charset, length, case or reserved-word check anywhere. Document ids are strictly regex-validated by contrast.

## Impact

Two agents will produce `auth`, `Auth` and `authentication` and nothing objects.

## Proposed default

Validate against `^[a-z][a-z0-9-]*$` and normalise case.

## Actors affected

- AI coding agent
- repository maintainer

## Evidence

- `src/docir/modules/tags/application/services/tag_service.py:43-52`
- `src/docir/modules/documents/domain/value_objects/identifiers.py:21`

---

Migrated from the discovery gap register (GAP-027); the register itself now lives in this store.
