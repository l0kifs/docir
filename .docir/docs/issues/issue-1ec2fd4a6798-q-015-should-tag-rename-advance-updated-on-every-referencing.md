---
created: '2026-07-30'
description: ADR-0006 argues staleness must be honest human re-verification; a bulk
  administrative edit silently forges it.
id: issue-1ec2fd4a6798
owner: maintainer
related:
- issue-9ed4905e0db8
status: resolved
tags:
- tags
- material
title: Q-015 — Should `tag rename` advance `updated` on every referencing document
type: issue
updated: '2026-07-30'
---

# Q-015 — Should `tag rename` advance `updated` on every referencing document

**Gap:** GAP-020 · **Also resolves:** — · **Audience:** repo maintainer
**Blocking:** no · **Rank:** 15 · **Asked:** — · **Answered:** 2026-07-28
**Authority:** repo maintainer (directed the work; the question was never answered separately, so the recorded assumption was acted on)

## Question

Should `tag rename` advance `updated` on every referencing document? It resets the staleness clock for any document without an explicit `verified` date.

## What the system does today

tag_service.py:77/99 set `updated = today`; `stale_reference_date()` falls back to `updated` (document.py:73-75). A classification edit makes overdue documents look freshly reviewed.

## Proposed answer

Do not advance `updated` for edits that change no content; or measure staleness from `verified` only, treating never-verified docs as stale from `created`.

## Why it matters

ADR-0006 argues staleness must be honest human re-verification; a bulk administrative edit silently forges it.

## Answer

No — it was unintended, and the reset is gone. `tag rename` and `tag rm --force` rewrite the classification without advancing `updated`, matching `check --fix` and `delete --force`. The alternative proposal (measure staleness from `verified` only) was rejected: it would mark every never-verified document stale from `created`, turning the warning on for the whole corpus on adoption — GAP-006's failure mode. See GAP-020.

---

Migrated from the discovery question queue (Q-015); the queue itself now lives in this store.
