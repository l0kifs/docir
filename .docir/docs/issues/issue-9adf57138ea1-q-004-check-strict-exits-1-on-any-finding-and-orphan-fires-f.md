---
created: '2026-07-30'
description: A team that adopts the documented gate gets a red build on day one and
  will remove it — which also removes the duplicate-id detection that is the gate's
  stated purpose and the…
id: issue-9adf57138ea1
owner: maintainer
related:
- issue-9cb85759076d
status: resolved
tags:
- integrity
- blocking
title: Q-004 — `check --strict` exits 1 on any finding, and `orphan` fires for every
  document with no…
type: issue
updated: '2026-07-30'
---

# Q-004 — `check --strict` exits 1 on any finding, and `orphan` fires for every document with no…

**Gap:** GAP-006 · **Also resolves:** — · **Audience:** repo maintainer
**Blocking:** yes · **Rank:** 4 · **Asked:** 2026-07-26 · **Answered:** 2026-07-26
**Authority:** repo maintainer (directed the fix; proposed severity split adopted as-is)

## Question

`check --strict` exits 1 on any finding, and `orphan` fires for every document with no relations — the default state of a new document — so the advertised CI gate fails on a healthy corpus. Which findings are meant to block a merge?

## What the system does today

OBSERVED: a fresh store with two unrelated, otherwise-healthy documents exits 1 from two `orphan` findings. No severity, no `--only <kind>`, no ignore file. Evidence: cli/app.py:439-440, graph_checks.py:173-192.

## Proposed answer

Severity on the finding: error = duplicate-id, dangling, malformed; warning = orphan, cycle, layering, stale, unknown-type. `--strict` fails on errors; `--strict=all` keeps today's behaviour.

## Why it matters

A team that adopts the documented gate gets a red build on day one and will remove it — which also removes the duplicate-id detection that is the gate's stated purpose and the only automated defence against Q-001 and Q-002.

## Answer

ANSWERED 2026-07-26 by implementation: errors = duplicate-id/dangling/malformed, warnings = orphan/cycle/layering/stale/unknown-type, --strict gates on errors, --strict-all preserves the old behaviour. See GAP-006 resolution.

---

Migrated from the discovery question queue (Q-004); the queue itself now lives in this store.
