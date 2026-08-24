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
status: resolved
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

## How it shipped

Shipped as `docir context "<task>" --also "<phrasing>"`, repeatable. adr-27c63ad02695 decided
docir generates nothing; this is the half that replaces what it closed.

## Measured

`benchmarks/example_fixture.yaml` against docir's own corpus, one hypothetical answer added per
task:

| queries | recall@5 | prec@5 | MRR |
|---|---|---|---|
| task only | 0.88 | 0.20 | 0.63 |
| task + hypothetical | **1.00** | 0.23 | **0.75** |
| hypothetical only | 1.00 | 0.23 | 0.75 |

This is what pseudo-relevance feedback could not be. adr-46b69a581c65 lost 0.13 recall because
it rewrote *from the corpus's top hits*, inheriting the first pass's mistakes; a rewrite that
comes from outside the ranking can rescue the queries the first pass got wrong.

**The third row is the uncomfortable one.** On these eight tasks the literal question adds
nothing once a good hypothetical exists. The task is still sent, because a *bad* hypothetical
alone would be catastrophic while a bad one fused with the question degrades gracefully — but
nothing here measures that, and it is the case worth measuring next.

**Limitation, and it is not small.** One annotator wrote the corpus, the judgments and the
hypotheticals, knowing all three. That shows the mechanism works; it does not size the gain a
stranger would see.

## The three questions this section carried

- **How several queries fuse** — all lists at once, `fuse_many`. Fusing each query and then
  combining normalises away how *many* queries found a document, which is the signal.
- **Whether the first is weighted** — no. qmd doubles the caller's literal query against its
  own machine-written expansions, a correction for expansions being worse. Here every string
  comes from the caller and docir has no basis for ranking them.
- **What a caller sends** — unbounded, and documented rather than enforced. The skill says two
  or three phrasings help and five paraphrases fuse noise. A cap would be docir guessing at a
  budget the caller can see and it cannot.
