---
created: '2026-07-30'
description: Once-per-repo onboarding command reporting success while doing nothing.
id: issue-bdb7330441e6
owner: maintainer
related:
- issue-b8220546282c
status: resolved
tags:
- agents
- material
title: Q-011 — Should `docir agent install --agent <unknown>` fail? Today it is a
  silent no-op, while…
type: issue
updated: '2026-07-30'
---

# Q-011 — Should `docir agent install --agent <unknown>` fail? Today it is a silent no-op, while…

**Gap:** GAP-024 · **Also resolves:** — · **Audience:** repo maintainer
**Blocking:** no · **Rank:** 11 · **Asked:** — · **Answered:** 2026-07-28
**Authority:** repo maintainer (directed the work; the question was never answered separately, so the recorded assumption was acted on)

## Question

Should `docir agent install --agent <unknown>` fail? Today it is a silent no-op, while `docir init --profiles <unknown>` correctly raises and lists valid names.

## What the system does today

OBSERVED: `--agent claud` → prints [], exit 0, writes nothing. Evidence: agents/application/service.py:96-98 vs composition.py:177-180.

## Proposed answer

Raise AgentSetupError naming the valid targets, matching --profiles.

## Why it matters

Once-per-repo onboarding command reporting success while doing nothing.

## Answer

Yes, it should error. `_resolve` now raises `AgentSetupError` listing the valid targets, matching `docir init --profiles`. `update` uses the same path, so a typo is rejected there too. See GAP-024 resolution.

---

Migrated from the discovery question queue (Q-011); the queue itself now lives in this store.
