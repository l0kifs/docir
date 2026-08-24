---
code:
- src/docir/modules/indexing/domain/scoring.py
- src/docir/modules/documents/application/services/document_service.py
created: '2026-08-24'
description: context and search return score and similarity with none of the terms
  behind them, so an agent cannot tell a bad ranking from an empty corpus and ranking
  changes are debugged with print statements.
id: issue-d3278330eb63
owner: maintainer
related:
- ref-a3f4d3140e4e
- ref-0e14d7c32dbf
status: resolved
tags:
- retrieval
- cli
title: A ranked result cannot say why it ranked
type: issue
updated: '2026-08-24'
---

## What happens

A ranked result carries `score` and `similarity` and nothing about how either was reached.
`score` is rank-derived, so it cannot distinguish a perfect match from the only document in the
store; `similarity` answers "how close" but not "why is this one above that one".

The evidence that this is a missing feature rather than a preference: ref-0e14d7c32dbf exists
to teach a reader how to interpret two numbers. A reference document explaining an output is
the output working around itself.

## Why it matters to both readers

An **agent** needs to tell "nothing relevant exists" from "the relevant thing ranked badly".
`--min-score` answers the first; nothing answers the second, so an agent that gets a poor set
has no way to report why and falls back to reading more documents.

The **maintainer** has one rule about ranking — measure, then decide — and no way to see the
intermediate terms without editing the source. Every ranking question so far was answered by
adding print statements to a working tree.

## What the trace should carry

Everything the fusion already computes and drops: the FTS rank and its RRF term, the vector
rank and its RRF term, the raw cosine, the section whose vector won. For a graph-reached hit,
the seed it was pulled from and the edge kind — a hit that arrived through `supersedes` is a
different claim from one that arrived through `relates_to`, and today both read as `via_graph`.

`FusedScore` already holds the two RRF components and the similarity. The ranks are discarded
in `fuse`, and the graph provenance is discarded in expansion.

## How it shipped

Shipped as `--explain` on `context` and `search`.

- **`search`** got it too. Its trace is one rank and a BM25 score, which is thinner — but a
  flag that works on one read path and not its sibling is an asymmetry an agent cannot infer.
- **At a TTY it renders under the table**, one dim line per document. Not a column: the payload
  is five to seven keys and a table cell cannot hold it legibly.
- **The trace is not trimmed away, and its floats are rounded to six places** rather than the
  three the ranked view uses. Rounding a diagnostic is how you lose the digits that made it
  one; six is where two RRF terms differing in the fifth place stay distinguishable.

## What the trace carries

Everything the fusion already computed and discarded. `lexical_rank` and `semantic_rank` are
new on `FusedScore` — `fuse` had them as loop indices and threw them away — and each rides
beside its RRF component, because the component alone is `1/(k+rank+1)` and cannot be read back
without knowing `k`. So the trace names `rrf_k` too.

**Keys are omitted rather than nulled.** A document the FTS index never returned carries no
`lexical_rank`, and that absence is the most useful single fact about a hit that ranked badly:
it says the two halves of retrieval disagreed, and which one found it.

A graph-reached hit carries `via_graph_from` and `via_graph_route` instead —
`successor`, `related` or `mention`. `_neighbours_of` returned bare ids and lost that, so it
now returns pairs; the ordering it is careful about is untouched.

## Measured

`docir bench benchmarks/example_fixture.yaml` before and after: `context` 0.88 / 0.20 / 0.63,
`--expand 0` 0.75 / 0.18 / 0.60, `search` 0.62 / 0.15 / 0.54 — identical. A diagnostic that
moved the thing it measures would be worse than none, and this is the first change checked
with the instrument issue-c6d184704682 shipped.

Verified by use as adr-7d9fbbf976e8 requires: run against this store, the top hit for "why is
the embedding model swappable" reports `lexical_rank=7, semantic_rank=1` — the semantic half
carrying a document the wording barely matched, which is exactly the question the flag exists
to answer.
