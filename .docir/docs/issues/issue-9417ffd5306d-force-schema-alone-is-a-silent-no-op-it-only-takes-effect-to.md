---
created: '2026-07-30'
description: A user who reaches for the more specific-sounding flag gets nothing and
  no explanation.
id: issue-9417ffd5306d
owner: maintainer
related:
- adr-20eec6e2e2ca
- arch-90c90751344f
- ref-1509d5dbb4c3
- issue-fde9a7151bd1
status: resolved
tags:
- cli
- cosmetic
title: '`--force-schema` alone is a silent no-op; it only takes effect together with
  `--force`'
type: issue
updated: '2026-08-05'
---

**Class:** unstated · **Severity:** cosmetic
**Flow:** arch-90c90751344f · **Step:** docir init --force-schema without --force
**Question:** None · **Frequency:** any use of --force-schema without --force

## Finding

`--force-schema` alone is a silent no-op; it only takes effect together with `--force`.

## What happens today

OBSERVED. On a store with a customised schema, `docir init --force-schema` reported `schema_written: false` and left the file untouched, with no message. The coupling is not stated in either flag's help.

## Impact

A user who reaches for the more specific-sounding flag gets nothing and no explanation. Low harm — the failure is inaction, not damage — but it is the flag whose whole purpose is to overwrite, silently declining to.

## Proposed default

Treat `--force-schema` as implying `--force` for the schema, or say why it did nothing. Introduced with the issue-fde9a7151bd1 fix.

## Resolution

FIXED 2026-07-29. `--force-schema` stands alone: it names the schema specifically, so requiring `--force` as well meant the more precise flag silently did nothing, and someone replacing a schema had to regenerate the gitignore to do it. `--force` is unchanged.

## Actors affected

- repository maintainer

## Evidence

- `src/docir/entry_points/composition.py`
- `ref-1509d5dbb4c3 (discovery probe log)`

---

Migrated from the discovery gap register (GAP-049); the register itself now lives in this store.
