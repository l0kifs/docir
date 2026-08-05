---
created: '2026-07-30'
description: Directly negates the product's headline claim.
id: issue-996b567e5131
owner: maintainer
related:
- arch-f220a644d654
- ref-1509d5dbb4c3
status: resolved
tags:
- retrieval
- blocking
title: '`--limit` bounds the ranked seed set but not the response'
type: issue
updated: '2026-08-05'
---

**Class:** incorrect · **Severity:** blocking
**Flow:** arch-f220a644d654 · **Step:** graph expansion after ranking
**Question:** issue-8bcb6b7f8308 · **Frequency:** every `context` call against a corpus with relations

## Finding

`--limit` bounds the ranked seed set but not the response. One-hop graph expansion runs afterwards and appends neighbours with no cap.

## What happens today

OBSERVED. Three decisions each with two outgoing edges: `docir context "cache invalidation policy" --limit 3` returned **9** documents. Worst case is limit × (1 + max out-degree).

## Impact

Directly negates the product's headline claim. docir exists to be "token-cheap for agents" (README:46); `context` is the flagship command; its default limit is 5; and the caller has no way to bound what comes back. On a well-linked corpus — the corpus docir is built to encourage — the overrun grows with graph density, so the tool degrades exactly as it is adopted successfully.

## Proposed default

Apply `limit` to the final result, or add a separate explicit budget for graph-expanded neighbours (e.g. `--expand N`, default 0 or 1) and document the interaction.

## Resolution

FIXED 2026-07-26. `--limit` is now a hard ceiling on the response and graph expansion runs inside it: `--expand N` (default 2) reserves at most N slots for neighbours, expansion is breadth-first across seeds so one dense hit cannot spend the whole budget, and slots the graph does not use are backfilled with more ranked hits — so a result is always min(limit, what exists). `expand` is clamped below `limit`, so a seed can never be crowded out. Verified by replaying PROBE-5 against the real CLI: --limit 3 now returns 3 (was 9), --expand 0 disables the graph, --limit 1 returns 1 ranked hit. Pinned by TestContextBudget in tests/modules/documents/test_integration_documents.py, confirmed to FAIL (assert 9 == 3) against the reverted implementation.

## Actors affected

- AI coding agent

## Evidence

- `src/docir/modules/documents/application/services/document_service.py:260-273`
- `src/docir/modules/documents/application/services/document_service.py:297-307`
- `ref-1509d5dbb4c3 (discovery probe log)`

---

Migrated from the discovery gap register (GAP-005); the register itself now lives in this store.
