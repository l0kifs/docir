---
code:
- src/docir/modules/indexing/**
created: '2026-08-24'
description: HyDE and LLM-authored query variants are untested and now blocked on
  whether docir may ship a generative model at all; the model-free half was measured
  and rejected.
id: issue-fd086c0c6ab0
owner: maintainer
related:
- ref-a6db21f52427
- adr-d657a09b8c4a
- adr-46b69a581c65
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

## What was measured, and what is left

Narrowed on 2026-08-24. The half that needed no generative model was built, measured on three
corpora and rejected — adr-46b69a581c65. Pseudo-relevance feedback cost 0.13 recall@5 on
docir's own corpus, because the first pass is already good enough that rewriting only drifts.

What remains is the half that **does** need one: HyDE, and LLM-authored query variants. Both
are now blocked on a question larger than ranking — whether docir may depend on a generative
model at all. That is a decision about the offline promise, a bounded install and no network at
query time, and nothing measured so far bears on it: the feedback failure is specific to
feeding the corpus back to itself, and says nothing about a rewrite that comes from outside it.

So the honest state is not "untested" any more. One mechanism is answered. The other cannot be
tested until somebody decides docir is allowed to ship a generative model, which is an ADR
nobody has written and which this issue should not pretend to settle.

## What is not decided

- Whether expansion and HyDE are one feature or two. They share a model and nothing else.
- Whether the rewrite is cached per query string, and where that cache lives.
- Whether a store without the optional model degrades silently to today's behaviour or refuses
  the flag. Silent degradation is the failure mode the deterministic embedder already has.
