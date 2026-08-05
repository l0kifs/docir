---
created: '2026-07-30'
description: Detection is good; the exit is undocumented.
id: issue-ed49c1d03894
owner: maintainer
related:
- arch-90c90751344f
- issue-476b4e188fab
status: resolved
tags:
- integrity
- cosmetic
title: Documented as leaving `unknown-type` documents; the recovery path is not documented
type: issue
updated: '2026-08-05'
---

**Class:** unstated · **Severity:** cosmetic
**Flow:** arch-90c90751344f · **Step:** disabling a profile after documents of its types exist
**Question:** None · **Frequency:** unknown

## Finding

Documented as leaving `unknown-type` documents; the recovery path is not documented.

## What happens today

Such documents cannot be validated, are never stale, and are skipped by the layering check. No command re-keys or migrates them.

## Impact

Detection is good; the exit is undocumented. Same shape as issue-476b4e188fab.

## Proposed default

Document 're-enable the profile, or change the type by hand and reindex'.

## Resolution

DOCUMENTED 2026-07-29, as proposed. The agent guide's maintenance section now states the exit: re-enable the profile in `docs-schema.yaml`, or change the doc's `type` to one the schema knows, then `docir reindex` — and says why `check --fix` will not do it (it cannot tell which you meant). It also states what an unresolved one costs: the document cannot be validated, is never reported stale, and is skipped by the layering check.

## Actors affected

- repository maintainer

## Evidence

- `src/docir/modules/documents/domain/services/graph_checks.py:60-82`
- `CLAUDE.md`

---

Migrated from the discovery gap register (GAP-025); the register itself now lives in this store.
