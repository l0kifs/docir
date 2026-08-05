---
created: '2026-08-03'
description: 'Why docir has no reranker: three models and three shortlist widths all
  ranked worse than plain RRF fusion.'
id: adr-d657a09b8c4a
owner: maintainer
related:
- adr-927aa43d9635
- ref-a6db21f52427
- adr-ab9c454b760c
status: rejected
tags:
- retrieval
- embeddings
- architecture
title: Cross-encoder reranking, built and rejected on measurement
type: decision
updated: '2026-08-05'
---

## Context
A survey of the adjacent field (`ref-a6db21f52427`) listed "no reranking" as a
gap: Basic Memory ships cross-encoder reranking, qmd ships an LLM rerank, and
docir stops at RRF fusion of the lexical and semantic rankings.

The argument for it is sound in the abstract. docir's embedder is a
**bi-encoder**: the document's vector is computed at write time, without ever
having seen the query, which is what makes it precomputable. A **cross-encoder**
reads `(query, passage)` together in one pass and can separate two documents a
cosine finds equally on-topic when only one of them answers the question. It
cannot be precomputed, so it reorders a shortlist retrieval has already found —
it can improve ordering and can never lose a document fusion retrieved.

`fastembed`, already a dependency, ships six cross-encoders. The smallest
(`Xenova/ms-marco-MiniLM-L-6-v2`) is 80 MB. There was no packaging obstacle.

## Decision
**Built it, measured it, rejected it.** The prototype is not in the tree.

It was a `Reranker` port in `platform/embedding` with a fastembed adapter and a
model-free stand-in, an opt-in `--rerank` flag on `context` (CLI and MCP), a
shortlist of the top N fused candidates, one cross-encoder pass per candidate
over its best-matching section, and a separate `rerank_score` field so the
absolute meaning of `similarity` was left intact. It worked. It made retrieval
worse.

Measured on `benchmarks/` — 26 documents, 20 tasks, k=5 — against a baseline of
recall@5 **0.97** / MRR **0.97**:

| configuration | recall@5 | MRR |
|---|---|---|
| fusion only (shipped) | **0.97** | **0.97** |
| ms-marco-MiniLM-L-6-v2, shortlist 20 | 0.90 | 0.89 |
| ms-marco-MiniLM-L-12-v2, shortlist 20 | 0.90 | 0.85 |
| jina-reranker-v1-turbo-en, shortlist 20 | 0.93 | 0.89 |
| ms-marco-MiniLM-L-6-v2, shortlist 12 | 0.90 | 0.89 |
| ms-marco-MiniLM-L-6-v2, shortlist 8 | 0.93 | 0.89 |

Six configurations across two model families and three shortlist widths. Every
one lost, on both metrics. Narrowing the shortlist did not rescue it, which
rules out "too much noise promoted from the tail" and points at the reranker's
ordering itself being worse than RRF's on this corpus.

The wiring was verified before the result was believed: the scores were real
logits, the top hit was usually correct, and the ordering was descending. This
is a judgment failure, not a bug.

## Why it lost
These rerankers are trained on **question → web passage** relevance. docir's
queries are imperatives — "implement idempotency keys on the payment capture
endpoint" — and its corpus is terse design documents. The model returned −8 to
−11 for nearly every pair, and ordering among confidently-negative scores is
noise. On T12 it demoted the correct document from rank 3 to 4; on T01, from 3
to 4.

The other half of the answer is that there was little room. RRF over a strong
lexical index and per-section vectors (adr-927aa43d9635) already places the right
document first on 97% of the benchmark. A reranker has to be better than that
to help, and an off-the-shelf one trained on a different distribution is not.

## Consequences
- **Nothing shipped.** No flag, no dependency change, no dead code behind a
  setting nobody should enable. A feature measured worse is not preserved "just
  in case" — it is a footgun with documentation.
- **The gap stays open in `ref-a6db21f52427`, with a reason.** "docir has no
  reranking" is still true; "docir should add reranking" is now measured false
  for the off-the-shelf option, which is the part worth knowing.
- **What would change this decision**, in rough order of promise: a reranker
  fine-tuned on imperative-to-design-document pairs; an LLM reranker (what qmd
  does) rather than a cross-encoder, which is a different cost class; or a
  corpus large enough that fusion's 0.97 stops being the ceiling — the
  benchmark is 26 documents, and a reranker's value grows with how much noise
  the retriever leaves.
- **Re-measuring is cheap.** The prototype was about 250 lines across a port, an
  adapter, a flag and one shortlist stage. This document exists so the next
  person spends that on a different model rather than on rediscovering that
  MS MARCO does not fit.
- **The precedent is adr-ab9c454b760c run the other way.** There, measurement
  overturned a shipped default that looked fine; here it stopped one that
  sounded fine. Both directions of that gate matter, and only one of them is
  usually written down.
