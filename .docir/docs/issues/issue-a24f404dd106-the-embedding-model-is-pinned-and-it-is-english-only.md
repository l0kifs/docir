---
code:
- src/docir/platform/embedding/**
- src/docir/config/settings.py
created: '2026-08-24'
description: bge-small-en-v1.5 is compiled in as the only real embedder, so a corpus
  not written in English retrieves worse than plain full-text search, with nothing
  to report it.
id: issue-a24f404dd106
owner: maintainer
related:
- ref-a6db21f52427
- adr-ab9c454b760c
- ref-e7534f1c812d
status: open
tags:
- embeddings
- retrieval
title: The embedding model is pinned, and it is English-only
type: issue
updated: '2026-08-24'
---

## What happens

`bge-small-en-v1.5` is compiled in as *the* embedder. The only alternative docir offers is
`DOCIR_EMBEDDER=deterministic`, which ref-e7534f1c812d measures at recall@5 0.80 — **below the
0.83 plain `search` manages with no vectors at all**. So a corpus written in Russian, Kazakh,
Chinese or Japanese has two options, and both are worse than turning semantic retrieval off.

## Why it is invisible

Nothing reports it. There is no finding, no warning, and no field in `check` that can name it:
the vectors are computed, stored and fused exactly as designed, and only their *meaning* is
degraded. A user sees `context` returning plausible-looking results with low `similarity` and
has no way to tell that from a corpus with genuinely nothing relevant in it — the one
distinction ref-0e14d7c32dbf exists to make.

This is why it reads as a configuration gap and is really an adoption gap. It costs nothing
until somebody writes documents in their own language, and then it costs them the feature.

## Why the fix is smaller than it looks

The machinery for *changing* embedder already exists, because adr-ab9c454b760c had to build it:
`embeddings.model_id` is written with every vector, `active_vectors(model_id)` returns only
matching rows, and a foreign or NULL id reads as dirty rather than as a dimension mismatch. A
switch therefore recomputes on the next write or `embed --flush` instead of raising.

What is missing is the setting that would let anyone flip it, and a documented set of known-good
models with their dimensions and install weight.

## What is not decided

- Whether the selector is an env var, a `docs-schema.yaml` key, or store config. A schema key
  is committed and travels with the corpus, which is the property that matters here.
- Whether an unknown model id is refused at load or accepted on trust.
- Whether the default moves. Gap 10 in ref-a6db21f52427 says install weight and ranking quality
  are one decision rather than two, and a multilingual model is larger than the current default.
