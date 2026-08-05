---
created: '2026-07-30'
description: Launders the one trust signal the product offers.
id: issue-9ed4905e0db8
owner: maintainer
related:
- adr-bd7c4f3c5764
- arch-ccfcceeb35eb
status: resolved
tags:
- tags
- material
title: '`tag rename` sets `updated = today` on every referencing document, resetting
  the review clock'
type: issue
updated: '2026-08-05'
---

**Class:** incorrect · **Severity:** material
**Flow:** arch-ccfcceeb35eb · **Step:** tag rename / tag rm --force
**Question:** issue-1ec2fd4a6798 · **Frequency:** every tag rename, across every document carrying the tag

## Finding

Renaming a tag sets `updated = today` on every referencing document, which resets the staleness clock for any document without an explicit `verified` date.

## What happens today

`stale_reference_date()` falls back to `updated` when `verified` is unset (document.py:73-75), and tag_service.py:77/99 bump `updated`. A pure classification edit therefore makes overdue documents report as freshly reviewed.

## Impact

Launders the one trust signal the product offers. adr-bd7c4f3c5764 argues staleness must be honest human re-verification; an administrative bulk edit silently forges it.

## Proposed default

Do not advance `updated` for edits that change no document content; or measure staleness from `verified` only, treating never-verified documents as stale from `created`.

## Resolution

FIXED 2026-07-28 with the first of the two proposed options: `tag rename` and `tag rm --force` no longer advance `updated` on the documents they rewrite. The second option (measure staleness from `verified` only) was not taken — it would make every never-verified document stale from `created`, which turns the warning on for essentially the whole corpus on adoption. That is issue-9cb85759076d's failure mode. This is the third place the same rule has now been applied — `check --fix` and `delete --force` already left `updated` alone — so it is no longer a local judgement but a stated invariant, recorded in CLAUDE.md: a mechanical rewrite is not a human re-verification, and only an edit a person made to the content may move the clock. CLEANUP: with the timestamp gone, `TagService` no longer used its `Clock` at all. The dependency is removed rather than left dangling — it was injected solely to stamp the date this gap says it should not stamp. Attribution verified: re-introducing the bump fails both new tests.

## Actors affected

- document owner / steward
- repository maintainer

## Evidence

- `src/docir/modules/tags/application/services/tag_service.py:74-80`
- `97-102`
- `src/docir/modules/documents/domain/entities/document.py:73-75`

---

Migrated from the discovery gap register (GAP-020); the register itself now lives in this store.
