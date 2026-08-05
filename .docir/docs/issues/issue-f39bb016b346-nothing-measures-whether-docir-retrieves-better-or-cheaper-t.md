---
created: '2026-07-30'
description: 'This is why every gap in the register carries `frequency: unknown`,
  why the retrieval constants (25 FTS candidates, 0.9 similarity, 8000 chars, RRF
  k=60) cannot be tuned on…'
id: issue-f39bb016b346
owner: maintainer
related:
- issue-e183d47cdee1
- issue-8bcb6b7f8308
- issue-f01a7a585fc1
- issue-f1727f4cf63b
status: resolved
tags:
- docs
- blocking
title: Nothing measures whether docir retrieves better or cheaper than the alternatives
type: issue
updated: '2026-08-05'
---

**Gap:** issue-e183d47cdee1
**Blocking:** yes · **Rank:** 8 · **Asked:** 2026-07-26 · **Answered:** 2026-07-26
**Authority:** repo maintainer (directed the build; proposed answer adopted as-is)

## Question

Nothing in the repo measures whether docir retrieves better or cheaper than the alternatives it is compared against. What would count as evidence that it works — and is building that measurement in scope before further retrieval tuning?

## What the system does today

No telemetry, no counters, no benchmark harness, no logging of business events. The README's comparison table is explicitly labelled "Rough orientation, not a benchmark" (README:48).

## Proposed answer

One offline benchmark, no user telemetry needed: a fixture corpus, a set of task descriptions, and human-judged relevant documents. Measure recall@k and tokens-returned.

## Why it matters

This is why every gap in the register carries `frequency: unknown`, why the retrieval constants (25 FTS candidates, 0.9 similarity, 8000 chars, RRF k=60) cannot be tuned on evidence, and why the token cost of issue-8bcb6b7f8308 cannot be quantified.

## Answer

ANSWERED 2026-07-26 by implementation, exactly as proposed: an offline benchmark, no telemetry — fixture corpus, task descriptions, human-judged relevant documents, recall/precision/MRR and payload size per strategy. It settled the embedder default (issue-f01a7a585fc1) and is now the gate on retrieval changes. Re-based 2026-07-27 to 23 documents / 14 tasks after issue-f1727f4cf63b showed it could not observe the graph at all. The answer to "is measurement in scope before further retrieval tuning" proved to be yes twice over: the first build changed the default embedder, the re-base changed which figures support that decision. Impact statements in 05-gaps.yaml are still `frequency: unknown` — the benchmark measures retrieval quality, not how often a gap is hit in real use. That needs evidence ranks 1 and 5, which remain unavailable.

---

Migrated from the discovery question queue (Q-008); the queue itself now lives in this store.
