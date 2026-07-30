---
created: '2026-07-30'
description: Small per document, paid on every read.
id: issue-7a271eb0f21a
owner: maintainer
related:
- adr-20eec6e2e2ca
- arch-f220a644d654
status: open
tags:
- integrity
- cosmetic
title: GAP-042 — A random id is ~3x the length of a sequential one (`adr-3f9a2b1c7d4e`
  vs `adr-0007`),…
type: issue
updated: '2026-07-30'
---

# GAP-042 — A random id is ~3x the length of a sequential one (`adr-3f9a2b1c7d4e` vs `adr-0007`),…

**Class:** unstated · **Severity:** cosmetic · **Confidence:** observed
**Flow:** FLOW-002 · **Step:** every skeleton and every related edge, once random ids are the default
**Question:** None · **Frequency:** every context/query/search result

## Finding

A random id is ~3x the length of a sequential one (`adr-3f9a2b1c7d4e` vs `adr-0007`), and ids appear in every skeleton and in every `related` edge of every result. Nothing measures what that costs.

## What happens today

A deliberate, maintainer-approved trade: cross-branch collision-freedom bought with token length. Recorded because it runs against the product's own headline claim ("token-cheap for agents", README:46) and because GAP-001 means the size of the trade is unknown.

## Impact

Small per document, paid on every read. 48 bits is not obviously the right size — it was chosen for "thousands of documents" — but shortening it is not free either: 24 bits collides at ~3% by a thousand docs.

## Proposed default

Fold "tokens returned per result set" into the benchmark proposed for GAP-001, then pick the entropy deliberately instead of by default.

## Actors affected

- AI coding agent

## Evidence

- `src/docir/modules/documents/domain/value_objects/identifiers.py:23-25`
- `src/docir/entry_points/composition.py:50-56`

---

Migrated from the discovery gap register (GAP-042); the register itself now lives in this store.
