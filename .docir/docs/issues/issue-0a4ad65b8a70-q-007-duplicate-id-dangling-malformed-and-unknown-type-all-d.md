---
created: '2026-07-30'
description: Every confirmed failure mode in this analysis ends in a state the product
  detects and cannot exit, and the documented recovery contradicts the product's second
  thesis.
id: issue-0a4ad65b8a70
owner: maintainer
related:
- issue-476b4e188fab
- issue-fd547a293d01
status: resolved
tags:
- integrity
- blocking
title: Q-007 — duplicate-id, dangling, malformed and unknown-type all describe corrupt
  state, and no…
type: issue
updated: '2026-07-30'
---

# Q-007 — duplicate-id, dangling, malformed and unknown-type all describe corrupt state, and no…

**Gap:** GAP-012 · **Also resolves:** GAP-007 · **Audience:** repo maintainer
**Blocking:** yes · **Rank:** 7 · **Asked:** 2026-07-26 · **Answered:** 2026-07-26
**Authority:** repo maintainer (directed the fix; `check --fix` proposal adopted)

## Question

duplicate-id, dangling, malformed and unknown-type all describe corrupt state, and no command can fix any of them. Combined with "agents never edit markdown directly", how is a user meant to recover — and should `delete --force` strip the edges it breaks, the way `tag rm --force` already strips tags?

## What the system does today

`check` reports; nothing repairs. OBSERVED: after `delete issue-0001 --force`, adr-0001's file still reads `related: [issue-0001]`, and `update adr-0001 --set-title X` succeeds and re-persists the broken edge — Tier 0 validates only edges supplied in the current call. Evidence: document_service.py:190-206, validation.py:61-66; contrast tag_service.py:97-103.

## Proposed answer

(a) `delete --force` strips the edge from referencing documents in the same transaction — the pattern already exists for tags. (b) Add `docir check --fix` for the mechanical cases: re-issue one of a duplicated id pair (rewriting inbound edges), drop dangling edges, resync the counter.

## Why it matters

Every confirmed failure mode in this analysis ends in a state the product detects and cannot exit, and the documented recovery contradicts the product's second thesis.

## Answer

ANSWERED 2026-07-26 in part, completed 2026-07-28. Both halves are now implemented. (b) `docir check --fix` repairs duplicate ids and dangling edges. (a) `delete --force` strips the edge from each referencing document in the same transaction and names them in its output, so the dead edge is no longer created. It does not advance their `updated`, unlike `tag rm --force` — a link removed from underneath you is not a human re-verification (GAP-020 tracks the tag path doing the opposite). The recovery path remains for edges broken outside the CLI, which after this is the only way to break one. See GAP-007 resolution.

---

Migrated from the discovery question queue (Q-007); the queue itself now lives in this store.
