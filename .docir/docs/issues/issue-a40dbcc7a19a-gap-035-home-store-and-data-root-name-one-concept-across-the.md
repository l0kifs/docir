---
created: '2026-07-30'
description: Minor discoverability friction.
id: issue-a40dbcc7a19a
owner: maintainer
related:
- adr-20eec6e2e2ca
- arch-90c90751344f
status: resolved
tags:
- cli
- cosmetic
title: GAP-035 — 'home', 'store' and 'data root' name one concept across the CLI help,
  the README and…
type: issue
updated: '2026-07-30'
---

# GAP-035 — 'home', 'store' and 'data root' name one concept across the CLI help, the README and…

**Class:** misleading · **Severity:** cosmetic · **Confidence:** observed
**Flow:** FLOW-004 · **Step:** user-facing naming of the store
**Question:** None · **Frequency:** n/a

## Finding

'home', 'store' and 'data root' name one concept across the CLI help, the README and the ADRs.

## What happens today

`--home` help says 'Data root'; `init` help says 'store'; ADR-0009 says 'store'.

## Impact

Minor discoverability friction.

## Proposed default

Standardise on 'store' in user-facing text; keep `home` as the flag name.

## Resolution

FIXED 2026-07-29, as proposed. User-facing prose says "store"; `--home` keeps its name as the flag. The `--home` help no longer says "Data root", and the README's remaining "data root" phrasing is gone. ADRs are left as written — they are dated records, not live documentation.

## Actors affected

- repository maintainer

## Evidence

- `src/docir/entry_points/cli/app.py:58-61`
- `src/docir/entry_points/cli/app.py:102-108`

---

Migrated from the discovery gap register (GAP-035); the register itself now lives in this store.
