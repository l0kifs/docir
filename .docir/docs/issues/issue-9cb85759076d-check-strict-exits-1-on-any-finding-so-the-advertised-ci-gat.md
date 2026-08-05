---
created: '2026-07-30'
description: The one CI integration the product advertises cannot be adopted as documented.
id: issue-9cb85759076d
owner: maintainer
related:
- arch-0a3c2d6d54a6
- ref-1509d5dbb4c3
- issue-389dc5dac58a
- issue-b7ddde3ce860
status: resolved
tags:
- integrity
- blocking
title: '`check --strict` exits 1 on any finding, so the advertised CI gate fails on
  a healthy corpus'
type: issue
updated: '2026-08-05'
---

**Class:** misleading · **Severity:** blocking
**Flow:** arch-0a3c2d6d54a6 · **Step:** CI gate
**Question:** issue-9adf57138ea1 · **Frequency:** first CI run of any adopting repo

## Finding

`docir check --strict` exits 1 on any finding of any kind, and `orphan` fires for every document with no relations — the default state of a newly created document. There is no severity, no `--only <kind>`, and no ignore mechanism.

## What happens today

OBSERVED. A brand-new store with two unrelated, otherwise-healthy documents exits 1 from two `orphan` findings alone.

## Impact

The one CI integration the product advertises cannot be adopted as documented. A team that tries it gets a red build immediately and will remove the gate — which also removes duplicate-id and dangling detection, the gate's actual purpose and the only automated defence against issue-b7ddde3ce860 and issue-389dc5dac58a. It also contradicts the tier model: `check` is documented as producing warnings that never block, while `--strict` makes all of them blocking equally.

## Proposed default

Give findings a severity (`error`: duplicate-id, dangling, malformed; `warning`: orphan, cycle, layering, stale, unknown-type) and make `--strict` fail on errors only, with `--strict=all` for the current behaviour.

## Resolution

FIXED 2026-07-26. `CheckIssue` now carries a `severity`, derived from `kind` in `__post_init__` so a new check cannot forget to classify itself. `ERROR_KINDS` is duplicate-id / dangling / malformed — the corpus is broken; everything else is a warning about shape or age. `--strict` gates on errors only; `--strict-all` keeps the old fail-on-anything behaviour. Findings render red vs yellow at a TTY and expose `severity` in JSON. Verified by replaying PROBE-3 against the real CLI: two healthy unrelated documents now exit 0 under `--strict` (1 under `--strict-all`), while a forced delete that leaves a dangling edge exits 1. Pinned by test_check_strict_gates_ci, test_check_strict_fails_on_a_broken_graph and test_findings_carry_a_severity. Note: test_check_strict_gates_ci previously asserted the OPPOSITE ("an orphan doc is a Tier 1 issue: --strict now fails") — the old behaviour was encoded as intent, which is why the gap survived to be found by running the tool rather than by reading the tests.

## Actors affected

- CI job
- repository maintainer

## Evidence

- `src/docir/entry_points/cli/app.py:419-440`
- `src/docir/modules/documents/domain/services/graph_checks.py:173-192`
- `ref-1509d5dbb4c3 (discovery probe log)`

---

Migrated from the discovery gap register (GAP-006); the register itself now lives in this store.
