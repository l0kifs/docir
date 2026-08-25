---
created: '2026-08-25'
description: 'The release that made retrieval inspectable: a swappable model, a benchmark
  an adopter can run, a rank trace, and two ways to hand docir a better question.'
id: rel-0c8d261640f6
owner: maintainer
related:
- adr-7316abc6be93
- adr-4c21693aac55
- adr-b23dae55666f
- adr-27c63ad02695
- adr-46b69a581c65
- adr-716c2eeb4e51
- adr-bbfac38a82b6
- adr-7d9fbbf976e8
- ref-a3f4d3140e4e
status: published
tags:
- release
- retrieval
- cli
title: 0.18.0 — retrieval you can measure, see into, and steer
type: release_note
updated: '2026-08-25'
---

## What this release is about

Retrieval was a black box: you could not point it at your own corpus, could not see inside it,
and could not improve it without editing the source. 0.18.0 opens all three — a model you can
change (`embed_model:`), an instrument you can run (`docir bench`), a trace you can read
(`--explain`) — and adds a way to hand docir a better question (`context --also`,
`query --expr`).

Released 2026-08-25. The full text is in `CHANGELOG.md` and on the GitHub release; this
document exists for the half neither of those can hold — the edges.

## What an upgrader must do

Run `docir self upgrade`. No migrations, but the relation-kind registry gained a property, and
the index records the schema it was built against — until each store reindexes, `docir check`
reports six `schema-drift` findings, one per core kind. Peers in `stores.yaml` each need their
own reindex, as always.

Nothing is rewritten and no flag is retired. `embed_model:` is absent from every existing
schema, which means the default, so retrieval is byte-identical until you set it.

## Why it is a graph and not a second changelog

A changelog is a list; this release was an argument, and the argument is in the decisions it
links. Four of them record work that was **built and thrown away** — a reranker's successor, a
query rewriter, a weighting scheme, a generative dependency — and those are the entries a later
reader most needs, because they are the ones somebody will otherwise propose again.

Read the linked decisions rather than this document. It is an index.

## What it cost to be sure

Every ranking change in 0.18.0 was measured before it shipped, and the instrument that measured
them shipped in the same release. Two mechanisms were measured and rejected: pseudo-relevance
feedback lost 0.13 recall@5, and cross-encoder reranking had already lost more in 0.15.

Three defects were found by *using* the features rather than by reading them — a documented
mermaid bundle that no longer existed, three flags that reached no MCP tool, and a check that
called a problem good news. adr-7d9fbbf976e8 is the rule that came out of that, and it is the
one entry here that is about how the work is done rather than what it produced.
