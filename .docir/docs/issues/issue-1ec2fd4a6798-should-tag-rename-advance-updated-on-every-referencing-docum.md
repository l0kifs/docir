---
created: '2026-07-30'
description: ADR-0006 argues staleness must be honest human re-verification; a bulk
  administrative edit silently forges it.
id: issue-1ec2fd4a6798
owner: maintainer
related:
- issue-9ed4905e0db8
- adr-bd7c4f3c5764
- issue-9cb85759076d
status: resolved
tags:
- tags
- material
title: Should `tag rename` advance `updated` on every referencing document
type: issue
updated: '2026-08-05'
---

**Gap:** issue-9ed4905e0db8
**Blocking:** no · **Rank:** 15 · **Answered:** 2026-07-28
**Authority:** repo maintainer (directed the work; the question was never answered separately, so the recorded assumption was acted on)

## Question

Should `tag rename` advance `updated` on every referencing document? It resets the staleness clock for any document without an explicit `verified` date.

## What the system does today

tag_service.py:77/99 set `updated = today`; `stale_reference_date()` falls back to `updated` (document.py:73-75). A classification edit makes overdue documents look freshly reviewed.

## Proposed answer

Do not advance `updated` for edits that change no content; or measure staleness from `verified` only, treating never-verified docs as stale from `created`.

## Why it matters

adr-bd7c4f3c5764 argues staleness must be honest human re-verification; a bulk administrative edit silently forges it.

## Answer

No — it was unintended, and the reset is gone. `tag rename` and `tag rm --force` rewrite the classification without advancing `updated`, matching `check --fix` and `delete --force`. The alternative proposal (measure staleness from `verified` only) was rejected: it would mark every never-verified document stale from `created`, turning the warning on for the whole corpus on adoption — issue-9cb85759076d's failure mode. See issue-9ed4905e0db8.

---

Migrated from the discovery question queue (Q-015); the queue itself now lives in this store.
