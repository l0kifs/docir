---
created: '2026-07-30'
description: Vocabularies drift and need consolidating; the registry can only grow.
id: issue-cc61d038cf8f
owner: maintainer
related:
- arch-ccfcceeb35eb
- issue-9ed4905e0db8
status: resolved
tags:
- tags
- material
title: Renaming a tag onto an existing key is rejected, so two tags cannot be merged
type: issue
updated: '2026-08-05'
---

**Class:** missing · **Severity:** material
**Flow:** arch-ccfcceeb35eb · **Step:** consolidating two tags
**Question:** None · **Frequency:** unknown

## Finding

Renaming a tag onto an existing key is rejected, so two tags cannot be merged.

## What happens today

tag_service.py:69-70 raises TagAlreadyExistsError. The only path is `tag rm --force` on one (losing the classification) then re-tagging by hand.

## Impact

Vocabularies drift and need consolidating; the registry can only grow. Coverage checklist item 'merge/deduplicate two records' is unmet.

## Proposed default

Allow rename-onto-existing as an explicit merge (`tag rename old new --merge`), rewriting documents and deduplicating keys.

## Resolution

FIXED 2026-07-29, as proposed. `tag rename old new --merge` folds `old` into an existing `new`: every document carrying `old` gets `new`, `old` leaves the registry, and the ids rewritten are returned so a bulk edit says what it touched. Without the flag the refusal stands, and its message now names `--merge` — a merge discards one of the two descriptions, which is not what someone fixing a typo means. THE CASE THAT MAKES IT MORE THAN A RELAXED CHECK: a document carrying *both* tags. The existing rewrite maps old->new positionally, so that document would have ended up with ('authn', 'authn'). Deduped with `dict.fromkeys`, which preserves order. Verified by reverting to the naive rewrite: the dedup test fails. `new`'s description is kept, not `old`'s — `new` is the tag being kept, so its wording is the one people chose for it. The merge inherits the staleness rule established by issue-9ed4905e0db8: rewritten documents keep their `updated`. A bulk classification edit across a whole vocabulary is the largest version of exactly the edit that rule exists for, and it is pinned by its own test. `--merge` onto a key that does *not* exist behaves as a plain rename rather than becoming a second code path; also pinned.

## Actors affected

- repository maintainer

## Evidence

- `src/docir/modules/tags/application/services/tag_service.py:69-70`

---

Migrated from the discovery gap register (GAP-028); the register itself now lives in this store.
