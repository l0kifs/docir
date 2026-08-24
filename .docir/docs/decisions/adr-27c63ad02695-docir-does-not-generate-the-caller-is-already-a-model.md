---
code:
- src/docir/platform/embedding/**
- src/docir/modules/documents/application/services/document_service.py
created: '2026-08-24'
description: Query rewriting belongs at the caller, which is a frontier model that
  has read the code, so docir ships no generative model and accepts several queries
  instead.
id: adr-27c63ad02695
owner: maintainer
related:
- adr-d657a09b8c4a
- adr-46b69a581c65
- adr-ab9c454b760c
- issue-fd086c0c6ab0
status: accepted
tags:
- retrieval
- embeddings
- architecture
title: 'docir does not generate: the caller is already a model'
type: decision
updated: '2026-08-24'
---

## Context

Two rejected mechanisms left the same question behind. adr-d657a09b8c4a measured cross-encoder
reranking and dropped it; adr-46b69a581c65 measured pseudo-relevance feedback and dropped that.
What remains in issue-fd086c0c6ab0 — HyDE, and LLM-authored query variants — cannot be measured
at all without deciding something larger first: **may docir depend on a text-generating model?**

It is a decision about what docir is, not about ranking. The README promises everything runs
locally, that only the first-run model download needs network, and that the semantic model is a
quantized 67 MB CPU-only embedder. `docir context` is the command an agent runs first, every
session, so anything on that path is paid on every task. qmd, the closest comparison, ships
three GGUF models totalling ~2 GB and generates on every query.

## Decision

**No.** Not as a dependency, and not as an optional extra.

The reason is not the install weight, though that is real. It is that **docir's caller is
already a generative model, and a better one.** When an agent runs `docir context "implement a
new auth endpoint"`, a frontier model is holding the conversation, has read the code, and knows
what the task actually is. Shipping a 0.5-1.5B quantized model to rewrite that same query is
adding a much weaker generator *underneath* a much stronger one, and asking it to guess at
context the caller already has and did not send.

An optional extra is not a smaller version of this. It is the same claim with a flag on it: the
code path, the tests, the docs and the failure modes all still exist, and the question "does
docir generate?" gets two answers depending on how you installed it.

## What replaces it

The rewriting belongs at the caller, so docir should **accept** rewritten queries rather than
produce them: several query strings in one call, fused the way the two backends already are.

That gives HyDE for free and better than docir could do it — an agent that writes a
hypothetical answer and passes it alongside the literal task is doing exactly what HyDE does,
with a model that knows the repository. It needs no dependency, adds no latency docir controls,
and is a strictly smaller change than the one it replaces.

It is **not** thereby approved. It is a ranking change, so it ships the way ranking changes
ship here: measured with `docir bench` first, on a corpus that matters, and rejected if the
numbers say so.

## What would reopen this

Evidence that the caller cannot do it — a measured case where an agent-supplied rewrite
underperforms a local model's. Not "HyDE is standard", and not a competitor shipping one.
qmd ships three; qmd is a search engine whose caller may be a shell.
