---
code:
- src/docir/platform/embedding/**
created: '2026-08-24'
description: The port declares a vector-width property nothing outside the embedding
  package consumes, and the fastembed adapter keeps it correct with a self-correcting
  field the library can answer directly.
id: issue-6618d3a9e868
owner: maintainer
related:
- issue-a24f404dd106
status: resolved
tags:
- embeddings
title: Embedder.dimension is declared and never read
type: issue
updated: '2026-08-24'
---

## What happens

`Embedder.dimension` is an abstract property on the port, implemented by both embedders, and
read nowhere outside `platform/embedding`. Nothing in `documents`, `indexing`, `persistence` or
the entry points asks an embedder how wide its vectors are — the storage layer does not need to
know, because `Embedding.to_bytes`/`from_bytes` handle any width and the columns are BLOBs.

## Why the fastembed adapter pays for it

`FastEmbedEmbedder` cannot answer the question until it has embedded something, so it holds
`_DEFAULT_DIMENSION = 384` as a starting value and overwrites it on the first `embed()` call.
That is a self-correcting field standing in for an answer the library already has: fastembed
exposes `get_embedding_size(model_name)`, which needs no inference pass.

So the property is wrong until first use, and nobody notices, because nobody reads it.

## Why it was left alone

Found while surveying issue-a24f404dd106 and deliberately not fixed there: removing a member
from a port touches every implementation, and that issue was about a corpus nobody could
retrieve. Nothing depends on the answer either way, which is exactly why it is a cleanup rather
than a defect.

## How it was resolved

Deleted, not wired. `Embedder.dimension` is gone from the port and from both implementations,
along with the fastembed adapter's `_DEFAULT_DIMENSION` and the `self._dimension = len(values)`
assignment that kept it honest.

An unread property is not an interface. Wiring it to `get_embedding_size()` would have made it
correct before first use, for a caller that does not exist — and left the port carrying a claim
about vector *shape* that nothing in the system needs, since storage is width-agnostic and the
one place two widths could disagree is checked inside `Embedding` where both are in hand.

## What the deterministic embedder kept

The deterministic embedder keeps its `dimension` **constructor argument**: that one is read, by
the hashing itself and by `model_id`, so two configurations cannot share a vector namespace.
Only the public accessor went. `test_the_configured_width_reaches_the_vector_and_the_model_id`
now asserts the width through the vector and the id rather than through an accessor — the two
things it still has to do.

Left undecided on purpose: whether `docir self status` should report the vector width beside
the model name. It was the one plausible caller and it is still speculative — the width is
knowable from the model, and nobody has asked.
