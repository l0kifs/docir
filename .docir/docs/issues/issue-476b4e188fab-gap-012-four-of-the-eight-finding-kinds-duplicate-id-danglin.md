---
created: '2026-07-30'
description: Every confirmed failure mode in this run (GAP-003, GAP-007, GAP-009)
  terminates in a state the product detects and cannot exit.
id: issue-476b4e188fab
owner: maintainer
related:
- arch-0a3c2d6d54a6
status: resolved
tags:
- integrity
- blocking
title: GAP-012 — Four of the eight finding kinds — duplicate-id, dangling, malformed,
  unknown-type —…
type: issue
updated: '2026-07-30'
---

# GAP-012 — Four of the eight finding kinds — duplicate-id, dangling, malformed, unknown-type —…

**Class:** missing · **Severity:** blocking · **Confidence:** observed
**Flow:** FLOW-003 · **Step:** after check reports a problem
**Question:** Q-007 · **Frequency:** whenever GAP-003 or GAP-009 fires

## Finding

Four of the eight finding kinds — duplicate-id, dangling, malformed, unknown-type — describe corrupt state, and no command can fix any of them. No `docir repair`, no `--fix`, no documented manual procedure.

## What happens today

The user hand-edits markdown and reruns reindex, guided by nothing.

## Impact

Every confirmed failure mode in this run (GAP-003, GAP-007, GAP-009) terminates in a state the product detects and cannot exit. That is also in direct tension with thesis #2, "agents never edit markdown directly" — recovery *requires* exactly that.

## Proposed default

`docir check --fix` handling the mechanical cases: re-issue one of a duplicated pair of ids (rewriting inbound edges), drop dangling edges, and resync the id counter.

## Resolution

FIXED 2026-07-26. `docir check --fix` (`MaintenanceService.repair`) repairs exactly what needs no guess about intent: duplicate ids are re-issued (the OLDEST file keeps the id, because existing edges were written against it and an edge cannot say which document it meant) and dangling edges are dropped from the canonical files. `malformed` and `unknown-type` are deliberately left alone — the first needs a human to say what the file was meant to be, the second is a schema decision — and are returned in `RepairResult.remaining`, so `check --fix --strict` still fails when a human is genuinely required. Repair does NOT advance `updated`: a mechanical fix is not a re-verification, and bumping it would launder the staleness clock (the GAP-020 failure mode). Verified against a store carrying all four kinds at once; pinned by six tests in tests/modules/documents/test_integration_maintenance.py plus two CLI tests. GAP-007 (delete --force leaving dead edges) is now recoverable, though still not prevented — it remains open as a separate concern.

## Actors affected

- support / operator
- repository maintainer

## Evidence

- `src/docir/modules/documents/application/services/maintenance_service.py:84-124`
- `src/docir/entry_points/cli/app.py:419-440`

---

Migrated from the discovery gap register (GAP-012); the register itself now lives in this store.
