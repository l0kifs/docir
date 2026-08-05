---
created: '2026-07-30'
description: '''Is this decision still current?'' is the question the relation graph
  most needs to answer, and it is the one direction not traversed.'
id: issue-e52de79d85ee
owner: maintainer
related:
- issue-5bfbc6f2699d
- issue-9152d83d9f78
status: resolved
tags:
- retrieval
- material
title: Should graph expansion follow incoming edges too?
type: issue
updated: '2026-08-05'
---

**Gap:** issue-5bfbc6f2699d
**Blocking:** no · **Rank:** 17 · **Asked:** 2026-07-27 · **Answered:** 2026-07-27
**Authority:** repo maintainer (directed the fix alongside issue-9152d83d9f78)

## Question

Should graph expansion follow incoming edges too? Today it is outgoing-only, so from a superseded document the document that superseded it is unreachable.

## What the system does today

`_augment_with_related` uses `outgoing()` only (document_service.py:301); `incoming()` exists and is used solely by delete (repositories.py:133-135).

## Proposed answer

Follow incoming supersedes/contradicts edges, or always attach the superseding document when one exists.

## Why it matters

'Is this decision still current?' is the question the relation graph most needs to answer, and it is the one direction not traversed.

## Answer

Yes — expansion follows incoming `supersedes`/`contradicts` as well, and puts them ahead of outgoing links so a tight `--expand` budget spends itself on "what replaces this?" first. Outgoing-only was a simplification, not a decision. See issue-5bfbc6f2699d resolution.

---

Migrated from the discovery question queue (Q-017); the queue itself now lives in this store.
