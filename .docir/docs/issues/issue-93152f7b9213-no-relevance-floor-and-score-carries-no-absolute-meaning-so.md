---
created: '2026-07-30'
description: An agent cannot distinguish relevant context from noise, so it either
  always trusts the results (and is misled on unrelated tasks) or never does.
id: issue-93152f7b9213
owner: maintainer
related:
- arch-f220a644d654
- ref-1509d5dbb4c3
- issue-996b567e5131
status: resolved
tags:
- retrieval
- material
title: No relevance floor, and `score` carries no absolute meaning, so noise reads
  like a match
type: issue
updated: '2026-08-05'
---

**Class:** misleading · **Severity:** material
**Flow:** arch-f220a644d654 · **Step:** interpreting context results
**Question:** issue-93dd537bbbbb · **Frequency:** every context query with no genuinely relevant document

## Finding

There is no relevance floor and the emitted `score` carries no absolute meaning, so "nothing relevant exists" is not an expressible answer.

## What happens today

OBSERVED. Against a store containing only "Postgres connection pooling", `docir context "how do I bake sourdough bread" --limit 3` returns that decision with score 0.0328 — the same magnitude a perfect match would score, because RRF depends only on rank position.

## Impact

An agent cannot distinguish relevant context from noise, so it either always trusts the results (and is misled on unrelated tasks) or never does. Compounds issue-996b567e5131: the response is both unbounded in size and unfiltered in quality.

## Proposed default

Emit the raw cosine similarity alongside the fused score and apply a floor (or expose `--min-score`), so an empty result set is possible.

## Resolution

FIXED 2026-07-28, as proposed, in both halves. `FusedScore` and `DocumentSummary` carry `similarity` — the raw cosine, which `fuse` previously computed, sorted by, and then discarded — and `context --min-score F` filters on it. PROBE-14 replayed: the sourdough query against the Postgres store returns `score 0.0164, similarity 0.4051`, and `--min-score 0.5` returns `[]`; the on-topic query scores `similarity 0.8951` and survives the same floor. The floor is on `similarity`, never on `score`: `score` is RRF and rank-derived, so it is structurally incapable of expressing relevance. That was the whole finding. TWO DELIBERATE EXEMPTIONS, both of which would otherwise break something real: (a) graph-reached neighbours are not filtered — a neighbour is present because a selected document links it, not because it scored, so judging it against the query would gut the graph feature; (b) a hit with no current vector (`similarity` absent) is not dropped — that is *unknown*, not zero, and dropping it would filter on the staleness of the embedding queue rather than on relevance. `docir embed --flush` closes (b). An absent `similarity` therefore means "not scored", so trimming had to round it rather than drop it — otherwise a genuine 0.0 became indistinguishable from no vector, which is exactly the distinction the floor rests on. Pinned by test_a_zero_similarity_survives_trimming. The default is unchanged: with no `--min-score`, `context` still always returns something. issue-93dd537bbbbb's recorded assumption (always-return-something is deliberate) is therefore preserved rather than overturned — the fix makes an empty result *expressible*, not automatic. The packaged agent guide now tells agents to judge on `similarity`, gives rough bands (>0.7 / 0.4-0.7 / <0.4) explicitly labelled as guides rather than thresholds, and says that an empty result is a real answer to report rather than a failure to work around.

## Actors affected

- AI coding agent

## Evidence

- `src/docir/modules/indexing/domain/scoring.py:36-73`
- `README.md:90-95`
- `ref-1509d5dbb4c3 (discovery probe log)`

---

Migrated from the discovery gap register (GAP-017); the register itself now lives in this store.
