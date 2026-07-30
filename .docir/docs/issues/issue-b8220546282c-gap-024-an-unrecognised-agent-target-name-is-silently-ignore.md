---
created: '2026-07-30'
description: A once-per-repo onboarding command that reports success while doing nothing;
  the user proceeds believing their agent knows how to drive docir.
id: issue-b8220546282c
owner: maintainer
related:
- adr-3a2d5ee7bc84
- arch-90c90751344f
- ref-1509d5dbb4c3
status: resolved
tags:
- agents
- material
title: 'GAP-024 — An unrecognised agent target name is silently ignored: no error,
  exit 0, nothing written'
type: issue
updated: '2026-07-30'
---

# GAP-024 — An unrecognised agent target name is silently ignored: no error, exit 0, nothing written

**Class:** incorrect · **Severity:** material · **Confidence:** observed
**Flow:** FLOW-004 · **Step:** docir agent install --agent <name>
**Question:** Q-011 · **Frequency:** any typo in --agent

## Finding

An unrecognised agent target name is silently ignored: no error, exit 0, nothing written.

## What happens today

OBSERVED. `docir agent install --agent claud` printed `[]`, exited 0, created no files. Two files away, `docir init --profiles bogus` correctly raises and lists the valid names.

## Impact

A once-per-repo onboarding command that reports success while doing nothing; the user proceeds believing their agent knows how to drive docir.

## Proposed default

Raise AgentSetupError naming the valid targets, matching --profiles.

## Resolution

FIXED 2026-07-28, as proposed. `_resolve` rejects any name not in `AGENT_TARGETS` and lists the valid ones, matching the `--profiles` message two files away. PROBE-13 replayed: `agent install --agent claud` now exits 2 with "unknown agent target(s): claud; available: claude, agents" where it printed `[]` and exited 0. `update` resolves through the same function, so a typo there is rejected too — it would otherwise have refreshed nothing and reported success, which is the same defect in the command people run more often. FIFTH instance of the encoded-defect trap, and the most explicit yet: the existing test was *named* `test_unknown_agent_is_ignored` and asserted the empty result. The behaviour was not merely unpinned, it was documented as intended in the suite. After GAP-006, GAP-008, GAP-040 and GAP-045, the pattern is reliable enough to act on: when a gap describes behaviour that "silently does nothing", grep the tests for a case asserting that nothing happens before assuming the tests are on your side.

## Actors affected

- repository maintainer

## Evidence

- `src/docir/modules/agents/application/service.py:91-105`
- `src/docir/entry_points/composition.py:177-180`
- `ref-1509d5dbb4c3 (discovery probe log)`

---

Migrated from the discovery gap register (GAP-024); the register itself now lives in this store.
