---
created: '2026-07-30'
description: There is a defensible argument for the current behaviour — "the issue
  this decision resolved is worth seeing even though it is closed" — but nothing states
  it, and the…
id: issue-9152d83d9f78
owner: maintainer
related:
- issue-8c37bf22ba3c
status: resolved
tags:
- retrieval
- blocking
title: Should graph expansion honour the inactive-status filter?
type: issue
updated: '2026-08-05'
---

**Gap:** issue-8c37bf22ba3c
**Blocking:** yes · **Rank:** 5 · **Asked:** 2026-07-26 · **Answered:** 2026-07-27
**Authority:** repo maintainer (chose "hidden", explicitly, over "returned but flagged")

## Question

A `resolved` issue is returned by `docir context` without `--include-resolved`, because graph expansion checks `archived` but not status — while `search` and `query` hide it correctly. Should graph-reached documents obey the same visibility rules as ranked ones?

## What the system does today

OBSERVED: issue-0001 (status resolved) referenced by adr-0001 is returned by `docir context auth --limit 5` with `via_graph: true`; the same document is hidden by `docir search auth` and `docir query`. Evidence: document_service.py:265-268 vs :297-307.

## Proposed answer

Yes — same predicate, extracted to one function so the two paths cannot diverge again. (If closed neighbours are deliberately valuable as context, say so and mark them.)

## Why it matters

There is a defensible argument for the current behaviour — "the issue this decision resolved is worth seeing even though it is closed" — but nothing states it, and the inconsistency across the four read paths suggests oversight rather than intent.

## Answer

An oversight — the filter applies. Asked as a two-option choice (hide the closed neighbour, matching the other three read paths, vs return it marked `inactive` so the "issue this decision resolved" stays visible); the maintainer chose hide. One `_is_visible` predicate now serves both the ranked and the graph path. `--include-resolved` remains the way to ask for closed work, and now governs both paths equally. See issue-8c37bf22ba3c resolution.

---

Migrated from the discovery question queue (Q-005); the queue itself now lives in this store.
