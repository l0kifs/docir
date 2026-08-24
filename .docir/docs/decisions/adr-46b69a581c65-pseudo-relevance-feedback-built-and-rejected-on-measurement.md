---
code:
- src/docir/modules/documents/application/services/document_service.py
created: '2026-08-24'
description: Rewriting a query with its top hits' own words costs 0.13 recall@5 on
  docir's corpus, because the first pass is already good enough that feedback only
  drifts.
id: adr-46b69a581c65
owner: maintainer
related:
- adr-d657a09b8c4a
- issue-fd086c0c6ab0
- issue-c6d184704682
status: accepted
tags:
- retrieval
- embeddings
title: Pseudo-relevance feedback, built and rejected on measurement
type: decision
updated: '2026-08-24'
---

## Context

adr-d657a09b8c4a rejected cross-encoder reranking on measurement and diagnosed *why* it failed:
docir's queries are imperatives ("implement a new auth endpoint") and its documents are terse
declaratives, so the two surface forms rarely meet. issue-fd086c0c6ab0 was opened because that
diagnosis is not the same as a fix — a reranker re-scores the mismatch after retrieval, while a
query rewrite removes it before.

Of the rewrites available, exactly one needs no generative model. HyDE and LLM-authored variants
put a generation on the read path and a GGUF in every install, against promises the README
makes. **Pseudo-relevance feedback** does not: take the best hits of the first pass, append their
titles and descriptions to the query, and embed *that* — the question restated in the vocabulary
the corpus actually uses.

## Decision

Built and rejected. Three corpora, three measurements, no case where it helped.

| corpus | metric | without | with |
|---|---|---|---|
| synthetic English, 26 docs | recall@5 / MRR | 0.97 / 0.97 | 0.97 / 0.97 |
| synthetic Russian, 26 docs | recall@5 / MRR | 0.75 / 0.63 | 0.72 / 0.62 |
| **docir's own, 160 docs** | recall@5 / MRR | **0.88 / 0.63** | **0.75 / 0.62** |

The real corpus is the one that decides, and it lost 0.13 recall@5. It also changed 6 of 8
result sets, so the mechanism is doing a great deal of work and getting it wrong.

## Why it fails here

Feedback helps when the first pass is mediocre and there is headroom to recover. docir's first
pass already returns the wanted document in the top five 88% of the time, so there is little to
gain and a great deal to drift toward: appending three descriptions pulls the query vector
toward the *centroid of the top hits* rather than toward the answer, and one irrelevant hit
among three poisons the rewrite.

The corpus shape works against it too. A docir `description` is a single abstract sentence
written to be a summary; three of them concatenated describe a neighbourhood, not a question.

## What stays open

Only the half that needs a generative model. issue-fd086c0c6ab0 keeps HyDE and LLM-authored
variants, and they are now blocked on something larger than themselves: whether docir may
depend on a generative model at all. That is a decision about the offline promise, not about
ranking, and nothing measured here bears on it — the failure above is specific to feeding the
corpus back to itself.

Do not reopen this half on the argument that "query expansion is standard". It was built, it
was measured on the corpus that matters, and it made retrieval worse.
