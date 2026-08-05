---
created: '2026-07-30'
description: An agent that reads output and then hand-writes frontmatter will use
  the wrong key.
id: issue-8d5b5b45e2fc
owner: maintainer
related:
- arch-3e305bc76ff0
status: resolved
tags:
- cli
- cosmetic
title: An edge's target key is `to` in frontmatter and `target` in JSON output
type: issue
updated: '2026-08-05'
---

**Class:** misleading · **Severity:** cosmetic
**Flow:** arch-3e305bc76ff0 · **Step:** reading a relation in two representations
**Question:** None · **Frequency:** n/a

## Finding

An edge's target key is `to` in frontmatter and `target` in JSON output.

## What happens today

markdown_store.py:167 writes `{to, kind}`; dto.py:17-25 emits `{target, kind}`.

## Impact

An agent that reads output and then hand-writes frontmatter will use the wrong key.

## Proposed default

Accept both keys on parse (`to` canonical on write).

## Resolution

FIXED 2026-07-29 exactly as proposed: `target` is accepted as a synonym for `to` on parse, `to` stays canonical on write. The alternative — renaming the JSON key to `to` — was rejected. It is a breaking change to the agent contract for a naming nit, and emitting both keys would add bytes to every edge in every skeleton, which is measurable now (adding one field to ranked hits cost 4.7% of a `context` payload). Accepting both on input costs nothing and removes the actual harm: an agent that reads `{target, kind}` from output and hand-writes it into frontmatter used to get "missing a 'to' id". Files do not churn.

## Actors affected

- AI coding agent

## Evidence

- `src/docir/platform/filesystem/markdown_store.py:156-168`
- `src/docir/modules/documents/application/dto.py:17-25`

---

Migrated from the discovery gap register (GAP-034); the register itself now lives in this store.
