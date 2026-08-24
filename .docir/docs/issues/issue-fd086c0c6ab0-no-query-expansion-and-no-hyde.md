---
code:
- src/docir/modules/indexing/**
created: '2026-08-24'
description: 'Both halves are answered: the model-free rewrite measured worse, and
  generation is closed by adr-27c63ad02695 — what remains is accepting caller-supplied
  queries.'
id: issue-fd086c0c6ab0
owner: maintainer
related:
- ref-a6db21f52427
- adr-d657a09b8c4a
- adr-46b69a581c65
- adr-27c63ad02695
status: open
tags:
- retrieval
- embeddings
title: context takes one query, and the caller has better ones
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

Answered on 2026-08-24, in two halves and not the way this issue expected.

The model-free half was built, measured on three corpora and rejected — adr-46b69a581c65.
Pseudo-relevance feedback cost 0.13 recall@5 on docir's own corpus: the first pass is already
right 88% of the time, so rewriting from the top hits mostly amplifies the 12% where it was not.

The half that needs a generative model is **closed by adr-27c63ad02695**, and the reason is
not cost. docir's caller is already a frontier model that has read the code and knows the task;
a 0.5-1.5B quantized rewriter underneath it would be guessing at context the caller had and did
not send. So docir generates nothing.

## What this issue becomes

Not "add HyDE" but **accept it**: several query strings in one `context` call, fused the way
the two backends already are. An agent that writes a hypothetical answer and passes it beside
the literal task is doing HyDE, with a better model and no dependency.

That is a ranking change and ships like one — measured with `docir bench` first, on a corpus
that matters, and dropped if the numbers say so. Two mechanisms have already been dropped that
way, which is the point of having the instrument.

## What is not decided

All three questions this section carried assumed a model docir now will not ship, so they are
moot rather than answered. What replaces them is smaller:

- **How several queries fuse.** RRF already fuses two *backends*; fusing N queries is the same
  operation one level out, and whether each query's lists fuse first or all lists fuse at once
  changes which document wins a tie.
- **Whether one query is weighted above the others.** qmd gives the caller's literal query
  double weight against its own expansions. Here every string comes from the caller, so there
  may be no reason to rank them — or the first may still deserve to be the anchor.
- **What a caller sends.** An agent that passes five paraphrases of one question will retrieve
  five times and fuse noise. Whether that is docir's problem to bound, or the caller's to not
  do, is unanswered and worth answering before the flag exists.
