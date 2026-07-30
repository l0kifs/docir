---
created: '2026-07-30'
description: An agent asking for current context receives closed work items it was
  promised it would not see, and cannot tell which results honoured the filter.
id: issue-8c37bf22ba3c
owner: maintainer
related:
- arch-f220a644d654
- ref-1509d5dbb4c3
status: resolved
tags:
- retrieval
- material
title: GAP-004 — The inactive-status filter is enforced on three read paths and skipped
  on the fourth
type: issue
updated: '2026-07-30'
---

# GAP-004 — The inactive-status filter is enforced on three read paths and skipped on the fourth

**Class:** incorrect · **Severity:** material · **Confidence:** observed
**Flow:** FLOW-002 · **Step:** graph expansion
**Question:** Q-005 · **Frequency:** any context query whose seed documents link to a closed document

## Finding

The inactive-status filter is enforced on three read paths and skipped on the fourth. `context`'s graph expansion checks `archived` but not status.

## What happens today

OBSERVED. A `resolved` issue referenced by a decision is returned by `docir context` without `--include-resolved`, while `docir search` and `docir query` correctly hide it.

## Impact

An agent asking for current context receives closed work items it was promised it would not see, and cannot tell which results honoured the filter.

## Proposed default

Apply the same visibility predicate in `_augment_with_related` as in the fusion loop; extract it to one function so they cannot diverge again.

## Resolution

FIXED 2026-07-27, as proposed. `DocumentService._is_visible` is now the single predicate (archived + inactive status) and both the fusion loop and graph expansion call it; `_augment_with_related` takes `include_inactive` so the caller's flag reaches the graph path. The maintainer chose *hidden* over *returned-but-flagged*: a graph-reached closed document is now indistinguishable in policy from a ranked one, which is what the other three read paths already promised. Pinned by test_resolved_neighbour_does_not_leak_through_the_graph (a `resolved` issue reachable only via its decision's edge) and test_resolved_neighbour_returns_when_ explicitly_asked_for (the same issue under `--include-resolved`). Attribution verified: reverting only the predicate call fails the first test and leaves the other two passing. Consequence accepted: "the issue this decision resolved" no longer rides along for free. `--include-resolved` is the way to ask for it.

## Actors affected

- AI coding agent

## Evidence

- `src/docir/modules/documents/application/services/document_service.py:297-307`
- `src/docir/modules/documents/application/services/document_service.py:265-268`
- `ref-1509d5dbb4c3 (discovery probe log)`

---

Migrated from the discovery gap register (GAP-004); the register itself now lives in this store.
