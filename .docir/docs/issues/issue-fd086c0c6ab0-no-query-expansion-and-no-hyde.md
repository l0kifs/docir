---
code:
- src/docir/modules/indexing/**
created: '2026-08-24'
description: The caller's task string reaches both backends unmodified, and adr-d657a09b8c4a
  is read as having answered this when it answered cross-encoder reranking.
id: issue-fd086c0c6ab0
owner: maintainer
related:
- adr-d657a09b8c4a
- ref-a6db21f52427
- kind: depends_on
  to: issue-c6d184704682
status: open
tags:
- retrieval
- embeddings
title: No query expansion and no HyDE
type: issue
updated: '2026-08-24'
---

## What happens

docir sends the caller's task string, unmodified, to FTS5 and to the embedder. Nothing rewrites
it, splits it into differently-worded variants, or converts it into the shape of the documents
before it is embedded.

## Why adr-d657a09b8c4a does not cover this

That decision rejected *off-the-shelf cross-encoder reranking* on measurement, and is being read
as having answered the whole retrieval frontier. It did not — and the reason it matters is that
it **diagnosed** a problem it does not fix.

Its finding: docir's queries are imperatives ("implement a new auth endpoint") and its documents
are terse declaratives, so the two surface forms rarely meet, and the reranker scored nearly
every pair in a band where ordering is noise. A reranker re-scores that mismatch *after*
retrieval. A rewrite removes it *before* — HyDE by drafting a hypothetical answer and embedding
that instead of the question, expansion by asking several differently-worded questions and
fusing the results.

Different mechanism, same diagnosis. Reopening this is not re-litigating adr-d657a09b8c4a.

## Constraints on any attempt

- **Measured, not argued.** A reranker was rejected on numbers, so its replacement cannot be
  accepted on plausibility. The instrument for that does not exist for adopters yet.
- **Never a hard dependency.** Offline operation, no network at query time and a bounded install
  are promises the README makes. A generative model in the read path is opt-in or it does not
  ship.
- **Latency is part of the result.** A rewrite that costs a generation per query competes with
  the interpreter-startup cost already recorded elsewhere, and `context` is the command an agent
  runs first, every session.

## What is not decided

- Whether expansion and HyDE are one feature or two. They share a model and nothing else.
- Whether the rewrite is cached per query string, and where that cache lives.
- Whether a store without the optional model degrades silently to today's behaviour or refuses
  the flag. Silent degradation is the failure mode the deterministic embedder already has.
