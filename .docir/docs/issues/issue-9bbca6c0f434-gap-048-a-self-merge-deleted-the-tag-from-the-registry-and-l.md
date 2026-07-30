---
created: '2026-07-30'
description: Data corruption reachable from a plausible command, shipped in 0.7.0.
id: issue-9bbca6c0f434
owner: maintainer
related:
- arch-ccfcceeb35eb
- ref-1509d5dbb4c3
status: resolved
tags:
- tags
- material
title: GAP-048 — A self-merge deleted the tag from the registry and left every document
  still carrying…
type: issue
updated: '2026-07-30'
---

# GAP-048 — A self-merge deleted the tag from the registry and left every document still carrying…

**Class:** incorrect · **Severity:** material · **Confidence:** observed
**Flow:** FLOW-005 · **Step:** docir tag rename X X --merge
**Question:** None · **Frequency:** any self-merge; also `tag rename X X` without --merge, same path

## Finding

A self-merge deleted the tag from the registry and left every document still carrying it, while reporting success.

## What happens today

OBSERVED and FIXED the same day. `tag rename auth auth --merge` returned `{"renamed":["auth","auth"],"documents":["adr-0001"]}`, `tag list` was empty, and the document still read `tags: [auth]` — the corpus was left in exactly the `unknown-tag` state `check` reports. `uow.tags.delete(old)` runs unconditionally, and the document rewrite maps `old -> new`, a no-op when they are the same string, so nothing restored the entry.

## Impact

Data corruption reachable from a plausible command, shipped in 0.7.0. Self-inflicted: introduced by the GAP-028 merge four commits earlier, whose tests covered merging two *different* tags and never the degenerate case.

## Proposed default

Reject `old == new` before opening the unit of work.

## Resolution

FIXED 2026-07-29. `rename` rejects `old == new` with a ValidationError before the unit of work opens, for both the plain and the `--merge` form. Pinned by two tests that assert the registry and the document survive and that `check` reports no `unknown-tag`. The general lesson, and the reason the delta pass earns its keep: a feature added to close a gap is itself new surface, and its own degenerate cases are unexamined. The GAP-028 tests asked "does merging two tags work?" and never "what if they are the same tag?".

## Actors affected

- repository maintainer
- AI coding agent

## Evidence

- `src/docir/modules/tags/application/services/tag_service.py`
- `ref-1509d5dbb4c3 (discovery probe log)`

---

Migrated from the discovery gap register (GAP-048); the register itself now lives in this store.
