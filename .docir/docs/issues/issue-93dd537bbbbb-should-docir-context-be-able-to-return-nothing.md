---
created: '2026-07-30'
description: Compounds Q-003 — the response is unbounded in size and unfiltered in
  quality.
id: issue-93dd537bbbbb
owner: maintainer
related:
- issue-93152f7b9213
- issue-8bcb6b7f8308
status: resolved
tags:
- retrieval
- material
title: Should `docir context` be able to return nothing?
type: issue
updated: '2026-08-05'
---

**Gap:** issue-93152f7b9213
**Blocking:** no · **Rank:** 9 · **Answered:** 2026-07-28
**Authority:** repo maintainer (directed the work; the question was never answered separately, so the recorded assumption below was preserved rather than overturned)

## Question

Should `docir context` be able to return nothing? There is no similarity floor, and the RRF `score` is rank-derived so it is ~identical for a perfect and a nonsense match.

## What the system does today

OBSERVED: against a store containing only "Postgres connection pooling", `context "how do I bake sourdough bread" --limit 3` returns it with score 0.0328. Evidence: scoring.py:36-73, document_service.py:257.

## Proposed answer

Emit raw cosine alongside the fused score and support `--min-score`, so an empty result is expressible.

## Why it matters

Compounds issue-8bcb6b7f8308 — the response is unbounded in size and unfiltered in quality.

## Answer

Both, and they do not conflict. The raw cosine is now emitted as `similarity` on every ranked hit, and `context --min-score F` filters on it — so an empty result is *expressible*. It is not automatic: with no `--min-score`, `context` still always returns something, which keeps the recorded assumption intact for anyone relying on it. The floor is on `similarity`, not on the fused `score`, because `score` is rank-derived and cannot carry relevance — that was the finding. Graph neighbours and hits without a current vector are exempt; see issue-93152f7b9213 resolution for why each would otherwise break.

## Assumption if unanswered

WAS: always-return-something is deliberate. Still true by default — the fix adds an opt-in floor rather than changing what `context` does when you do not ask for one.

---

Migrated from the discovery question queue (Q-009); the queue itself now lives in this store.
