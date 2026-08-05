---
created: '2026-07-30'
description: Under-return looks like corpus scarcity rather than filtering.
id: issue-e19a2fde1805
owner: maintainer
related:
- arch-f220a644d654
status: resolved
tags:
- retrieval
- cosmetic
title: '`search` fetches `limit * 2` candidates then filters, so it under-returns
  on a closed corpus'
type: issue
updated: '2026-08-05'
---

**Class:** unstated · **Severity:** cosmetic
**Flow:** arch-f220a644d654 · **Step:** search with many inactive documents in the head of the ranking
**Question:** None · **Frequency:** corpora with a high proportion of closed documents

## Finding

`search` fetches `limit * 2` candidates then filters; if more than half are inactive it returns fewer than `limit` with no indication why.

## What happens today

document_service.py:236-247.

## Impact

Under-return looks like corpus scarcity rather than filtering. The 2× factor is an unexplained constant.

## Proposed default

Filter in SQL, or loop until the limit is met or candidates are exhausted.

## Resolution

FIXED 2026-07-29 with the second option: the candidate pool doubles until the limit is met or the index is exhausted, so a short result means the corpus is short. Filtering in SQL was the alternative and was not taken — FTS5 does not know a document's status, so it would mean teaching the search adapter about `documents`, for a case a retry loop covers at no structural cost. The unexplained `2` is now `_SEARCH_OVERFETCH`, documented as a starting point rather than a bound. THE FIRST TEST DID NOT DISCRIMINATE, and only injecting the old behaviour revealed it: resolving a document re-indexes it, which moves its FTS row to the *back*, so equally-weighted closed documents drift behind the open ones and a fixed pool finds the open ones anyway. The fixture now gives the closed documents repeated query terms so BM25 ranks them first — the shape the finding actually describes. Recorded because the same trap will catch the next person writing a search test.

## Actors affected

- AI coding agent

## Evidence

- `src/docir/modules/documents/application/services/document_service.py:236-247`

---

Migrated from the discovery gap register (GAP-018); the register itself now lives in this store.
