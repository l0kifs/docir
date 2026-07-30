---
created: '2026-07-30'
description: 'Compounds Q-004: it guarantees a finding on the most natural modelling,
  which trains users to ignore `check` output entirely.'
id: issue-f2591bdbca13
owner: maintainer
related:
- issue-40d1792bc9f9
status: resolved
tags:
- integrity
- blocking
title: Q-006 — In the default `software` profile, linking a decision to the issue
  that motivated it…
type: issue
updated: '2026-07-30'
---

# Q-006 — In the default `software` profile, linking a decision to the issue that motivated it…

**Gap:** GAP-008 · **Also resolves:** — · **Audience:** repo maintainer
**Blocking:** yes · **Rank:** 6 · **Asked:** 2026-07-26 · **Answered:** 2026-07-27
**Authority:** repo maintainer (directed the work; the question itself was never answered separately, so this was implemented on the recorded assumption below and is open to reversal)

## Question

In the default `software` profile, linking a decision to the issue that motivated it produces a permanent `layering` violation (decision level 3 → issue level 1). Is that intended discouragement, or should the layering check apply only to dependency kinds rather than to every kind except supersedes/contradicts?

## What the system does today

OBSERVED: `adr-0001 related: [issue-0003]` → "layering violation: decision 'adr-0001' depends on lower-level issue 'issue-0003'". This is the pairing shown in the README's own quickstart output (README:78-81). Evidence: profiles.py:26-27/44-46, graph_checks.py:194-223, :26.

## Proposed answer

Restrict the check to `depends_on` (and `refines`). `relates_to` is the default kind applied to every bare id and asserts no dependency, so it should not be a layering signal.

## Why it matters

Compounds Q-004: it guarantees a finding on the most natural modelling, which trains users to ignore `check` output entirely.

## Answer

Implemented as proposed: the layering check now reads a dependency allowlist (`depends_on`, `refines`) instead of exempting supersedes/contradicts. `relates_to` — the kind every bare id becomes — no longer produces a violation, so the README quickstart pairing is clean. `implements` was also excluded, which the question did not ask about: it points implementation -> spec by nature and its direction carries no dependency claim. See GAP-008 resolution.

## Assumption if unanswered

WAS: the exempt-kind list is inverted and should be a dependency-kind allowlist. Acted on rather than answered — if the intent was in fact discouragement, this is the change to revert.

---

Migrated from the discovery question queue (Q-006); the queue itself now lives in this store.
