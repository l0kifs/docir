---
created: '2026-07-30'
description: Small per document, paid on every read.
id: issue-7a271eb0f21a
owner: maintainer
related:
- arch-1cfb1b212237
- arch-f220a644d654
- issue-e183d47cdee1
status: resolved
tags:
- integrity
- cosmetic
title: A random id is ~3x the length of a sequential one, and the cost is paid on
  every read
type: issue
updated: '2026-08-05'
---

**Class:** unstated · **Severity:** cosmetic
**Flow:** arch-f220a644d654 · **Step:** every skeleton and every related edge, once random ids are the default
**Question:** None · **Frequency:** every context/query/search result

## Finding

A random id is ~3x the length of a sequential one (`adr-3f9a2b1c7d4e` vs `adr-0007`), and ids appear in every skeleton and in every `related` edge of every result. Nothing measures what that costs.

## What happens today

A deliberate, maintainer-approved trade: cross-branch collision-freedom bought with token length. Recorded because it runs against the product's own headline claim ("token-cheap for agents", README:46) and because issue-e183d47cdee1 means the size of the trade is unknown.

## Impact

Small per document, paid on every read. 48 bits is not obviously the right size — it was chosen for "thousands of documents" — but shortening it is not free either: 24 bits collides at ~3% by a thousand docs.

## Proposed default

Fold "tokens returned per result set" into the benchmark proposed for issue-e183d47cdee1, then pick the entropy deliberately instead of by default.

## Actors affected

- AI coding agent

## Evidence

- `src/docir/modules/documents/domain/value_objects/identifiers.py:23-25`
- `src/docir/entry_points/composition.py:50-56`

---

Migrated from the discovery gap register (GAP-042); the register itself now lives in this store.

## Resolution

MEASURED 2026-07-30; entropy kept at 48 bits, now deliberately. `benchmarks/run.py` prices both halves of the trade. Cost: random ids are 7.1% of a `context` payload (131 of ~1856 chars) and switching to sequential would return 3.4% of it. Benefit: at 48 bits the collision probability is effectively zero out to 100,000 documents; at 32 bits it is 1.16% by 10,000, and at 24 bits 2.94% by 1,000. Dropping to 32 bits would return about 1% of a result set and buy a permanent ~1-in-86 chance of the exact failure `docir check --strict` exists to catch at merge time. That is a bad trade, so 48 stays. The measurement also found the benchmark itself was wrong: it built its store with the bare schema default (`sequential`), while `docir init` gives every real project `random`, so every token figure it had ever printed understated the shipped default by four characters per id. `context` is 464 tokens, not 448. Quality figures are unaffected. Full tables in benchmarks/README.md §3b.
