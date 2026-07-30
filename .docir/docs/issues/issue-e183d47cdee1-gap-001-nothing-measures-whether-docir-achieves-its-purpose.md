---
created: '2026-07-30'
description: Not a defect in the code; a defect in the ability to make decisions about
  the code.
id: issue-e183d47cdee1
owner: maintainer
related:
- arch-1cfb1b212237
- ref-1509d5dbb4c3
status: resolved
tags:
- docs
- blocking
title: GAP-001 — Nothing measures whether docir achieves its purpose. No telemetry,
  no counters, no…
type: issue
updated: '2026-07-30'
---

# GAP-001 — Nothing measures whether docir achieves its purpose. No telemetry, no counters, no…

**Class:** missing · **Severity:** blocking · **Confidence:** observed
**Flow:** None · **Step:** the whole product
**Question:** Q-008 · **Frequency:** n/a

## Finding

Nothing measures whether docir achieves its purpose. No telemetry, no counters, no benchmark harness, no logging of business events, no way to answer "did retrieval change what the agent did?"

## What happens today

The README's own comparison table is labelled "Rough orientation, not a benchmark" (README:48). The two central claims — better retrieval than RAG, cheaper than raw files — are unmeasured by the author.

## Impact

Not a defect in the code; a defect in the ability to make decisions about the code. It is why every other gap in this register has `frequency: unknown`, why the retrieval quality parameters (GAP-017, BR-026, BR-046 thresholds) cannot be tuned on evidence, and why there is no way to know whether GAP-005's token overrun matters in practice or is the dominant cost.

## Proposed default

Before tuning retrieval further, build one honest offline benchmark: a fixture corpus, a set of task descriptions, and the documents a human judges relevant. Measure recall@k and tokens-returned. It does not need telemetry from users.

## Resolution

FIXED 2026-07-26. `benchmarks/` now measures both claims offline — no telemetry, no users: 20-document corpus, 12 tasks with relevance judgments, recall/precision/MRR and payload size per retrieval strategy. Run with the default embedder and with DOCIR_EMBEDDER=fastembed to get the contrast. Results and their limits are in benchmarks/README.md. Deliberately not a pass/fail test: it prints numbers and exits 0, because a threshold set before the numbers are understood would just encode today's behaviour as intent (the mistake that let GAP-006 survive). The retrieval constants can now be tuned on evidence, and GAP-042 (what random ids cost in tokens) is now answerable.

## Actors affected

- repository maintainer

## Evidence

- `README.md:39-48`
- `ref-1509d5dbb4c3 (discovery probe log)`

---

Migrated from the discovery gap register (GAP-001); the register itself now lives in this store.
