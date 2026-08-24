---
code:
- src/docir/modules/indexing/domain/scoring.py
created: '2026-08-24'
description: Interleaving per-query rankings keeps what a correct extra phrasing finds
  while bounding what a wrong one costs — the only one of three fusion shapes that
  does both.
id: adr-4c21693aac55
owner: maintainer
related:
- kind: refines
  to: adr-b23dae55666f
- adr-27c63ad02695
- issue-fd086c0c6ab0
status: accepted
tags:
- retrieval
- embeddings
title: Several queries take turns rather than pooling their scores
type: decision
updated: '2026-08-24'
---

## Context

`--also` shipped fusing every query's backend lists into one RRF ranking. adr-b23dae55666f then
measured what a *wrong* phrasing costs — recall@5 0.88 → 0.25 — and established that weighting
the task cannot fix it, because weighting suppresses an extra query everywhere, including the
documents only it can find. That decision closed with one untested idea: bound a query's
**share** of the result rather than its score.

## Decision

With more than one query, the per-query rankings are **interleaved** rather than pooled. Each
query's best goes first, then each query's second, and so on, deduped. The caller's task holds
every Nth slot no matter what the others rank.

Measured against the same eight tasks and the same deliberately wrong hypothetical:

| configuration | pooled RRF | task weight ×2 | **interleaved** |
|---|---|---|---|
| task only | 0.88 | 0.88 | 0.88 |
| task + correct | **1.00** | 0.88 | **1.00** |
| task + wrong | 0.25 | 0.75 | **0.75** |
| task + correct + wrong | 0.69 | 0.81 | **1.00** |

It dominates both on every row. It keeps everything pooling had on a correct phrasing, matches
what weighting bought on a wrong one, and is the only one of the three that survives a caller
sending both — where pooling drowns and weighting merely dilutes.

## Why the shape works where the weight did not

They fail differently on purpose. A weight is applied to a query's *scores*, so lowering it
lowers every document that query found, including the ones nothing else found — which is
exactly the contribution `--also` exists for. Interleaving leaves every query's own ordering
intact and rations only how many slots it may fill, so a bad phrasing loses the argument about
*how much* of the result it gets without losing its best pick.

Put another way: pooling asks "which document has the most support", which a confident wrong
query wins by being confident. Taking turns asks "what does each query most want", which it
cannot win more than once.

## Consequences

One query is unaffected — `fuse` is what it always was, and `docir bench` scores identically
before and after (0.88 / 0.20 / 0.63).

The guidance adr-b23dae55666f forced can soften but not disappear. 0.75 against a baseline of
0.88 is still a real cost for a wrong guess, so `--also` remains for a caller that could defend
the answer it is guessing — it is no longer the 5:1 downside that made it close to unusable.

`FusedScore.score` stops being comparable across a multi-query result: the merged list is
ordered by turn, not by score, so a document in slot 2 may carry a lower score than one in slot
3. `similarity` is unaffected and remains the number with absolute meaning.
