---
created: '2026-07-30'
description: docir's headline claim is "token-cheap for agents" and `context` is the
  flagship command with a default limit of 5. The overrun scales with exactly the
  well-linked corpus the…
id: issue-8bcb6b7f8308
owner: maintainer
related:
- issue-996b567e5131
status: resolved
tags:
- retrieval
- blocking
title: Q-003 — `docir context --limit 3` returned 9 documents, because one-hop graph
  expansion runs…
type: issue
updated: '2026-07-30'
---

# Q-003 — `docir context --limit 3` returned 9 documents, because one-hop graph expansion runs…

**Gap:** GAP-005 · **Also resolves:** — · **Audience:** repo maintainer
**Blocking:** yes · **Rank:** 3 · **Asked:** 2026-07-26 · **Answered:** 2026-07-26
**Authority:** repo maintainer (chose "bound the response, add --expand N")

## Question

`docir context --limit 3` returned 9 documents, because one-hop graph expansion runs after the limit and is itself uncapped. Should `--limit` bound the whole response, or is it deliberately a seed-set size with expansion on top — and if so, what bounds the response an agent receives?

## What the system does today

OBSERVED: 3 decisions with out-degree 2, `--limit 3` → 9 results. Worst case is limit × (1 + max out-degree), growing with graph density. Evidence: document_service.py:260-273 (limit enforced), :297-307 (expansion, uncapped).

## Proposed answer

`--limit` bounds the final result. If expansion should be separately controllable, add `--expand N` with a small default and document the interaction.

## Why it matters

docir's headline claim is "token-cheap for agents" and `context` is the flagship command with a default limit of 5. The overrun scales with exactly the well-linked corpus the product encourages, so it worsens as adoption succeeds.

## Answer

ANSWERED 2026-07-26: bound the response, with --expand N for neighbour control. Implemented as reserved-then-backfilled slots. See GAP-005 resolution.

---

Migrated from the discovery question queue (Q-003); the queue itself now lives in this store.
