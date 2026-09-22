---
code:
- src/docir/platform/embedding/**
code_baseline:
  src/docir/platform/embedding/**: 3732fa1ff3cb
created: '2026-07-27'
description: Why a real embedding model is the default and the hashing embedder only
  the fallback.
id: adr-ab9c454b760c
owner: maintainer
related:
- kind: refines
  to: arch-1cfb1b212237
status: accepted
tags:
- embeddings
- retrieval
title: Semantic embeddings on by default
type: decision
updated: '2026-09-22'
verified: '2026-09-22'
verified_code:
  src/docir/platform/embedding/**: 3732fa1ff3cb
verified_content: 9f2f7a2f47ec
---

## Context
docir's pitch is retrieval by *meaning*: the README's comparison table claimed
"Retrieval by meaning ✅ (lexical + semantic)" against plain markdown's ❌ and
RAG's ✅. `docir context` fused an FTS5 (BM25) ranking with a cosine ranking over
embedding vectors, which is a real hybrid design.

The vectors, however, came from `DeterministicEmbedder` unless the user opted in
with `DOCIR_EMBEDDER=fastembed` and the `embeddings` extra. That embedder is
signed feature hashing over tokens: it scores similarity by **shared
vocabulary**, which is the same signal FTS5 already provides. Two sentences
meaning the same thing in different words score exactly zero:

```
0.000  'duplicate charges when the customer double-clicks pay'
       vs 'idempotency keys for payment capture'
```

So in a default install both halves of the "hybrid" measured the same thing, and
the claim on the front page described a configuration most users would not be
running. Nothing in the repo measured retrieval at all, so this had gone
unnoticed: every retrieval constant (the 25-candidate pool, RRF `k=60`, the 0.9
lint threshold, `--limit 5`) had been chosen without evidence.

A benchmark was built first, precisely so this decision would not be another
untested guess — 23 documents, 14 tasks with relevance judgments, half of them
deliberately phrased in words the documents never use (`benchmarks/`). The
numbers it gives are in *The measurement, and the instrument it needs*; the
short form is that the hybrid design was sound and the shipped default was not
exercising it.

## Decision
**Make `fastembed` a required dependency and the default embedder.**
`DOCIR_EMBEDDER=deterministic` selects the hashing embedder as an explicit
fallback. The `embeddings` extra is retained as a no-op so existing
`pip install docir[embeddings]` commands keep working.

The model is `BAAI/bge-small-en-v1.5` — quantized ONNX, CPU-only, 384-dim, run
locally. Nothing is sent anywhere and no API key exists.

**The README states the cost rather than hiding it**: ~64 MB of weights
downloaded once on first use, ~240 MB of dependencies (`onnxruntime`, `numpy`,
`tokenizers`, …). The "Works offline, nothing to run" row was amended to
"✅ after the model downloads once" — making the model required introduces a
one-time network step, and leaving that row unqualified would have replaced one
false claim with another.

**Vectors now record which model produced them.** `set_vector` writes
`embeddings.model_id`; `active_vectors(model_id)` returns only matching rows and
`dirty_ids(model_id)` treats a foreign or `NULL` model as dirty, so stale vectors
fall out of ranking and are recomputed on the next write or `docir embed
--flush`. This is a prerequisite, not a nicety: models differ in width, and
`Embedding.cosine_similarity` raises `dimension mismatch: 256 != 384` rather than
degrading, so without it the flip would have made `docir context` throw in every
existing store on first read. The `model_id` column had existed since migration
`0001` and was never written — a dead column that turned out to be load-bearing.

**The adapter is no longer excluded from the gates.** `fastembed.py` was excluded
from `ty` and omitted from coverage, with `# pragma: no cover` and no test
referencing it. Correct while it was opt-in; a hole the moment it became the
default, since CI installed the dependency and then exercised none of it.
Lifting the `ty` exclusion immediately surfaced a real diagnostic (the adapter
held its model as bare `object`), now fixed with a `_TextEmbedding` Protocol.
Tests that load the real model are marked `slow`. The model is downloaded to
`~/.docir/models` ([[adr-78090be868ec]]); CI pins `FASTEMBED_CACHE_PATH` and caches
that directory.

### Considered and rejected

- **Leave it opt-in and just document the caveat.** This was the first attempt,
  and the docs change is in git history. It is defensible — but it makes the
  headline feature something the user has to discover and enable, and the
  comparison table then has to carry a ⚠️ against the one row the product is
  named for. Correct documentation of a weak default is still a weak default.

### Prefer fastembed if importable, fall back silently otherwise.

Keeps the
install light, but a plain `pip install docir` would still have no semantic
retrieval, so the README could not honestly drop the caveat. It also makes
behaviour depend on what happens to be installed, which is the least debuggable
kind of default.

### A smaller or quantized-further model.

`bge-small` is already the small,
quantized tier. The remaining weight is `onnxruntime`, not the weights.

### Falling back to the hashing embedder at runtime when the model fails to load.

Rejected: it would mix vector spaces within one index. Dimension
mismatch raises, so the failure would be loud, but a *same-width* mismatch
would silently rank against meaningless vectors. The embedder is chosen once,
at container build, and never swapped mid-flight.

## Consequences
- Easier: semantic retrieval works from `pip install docir` with no flags;
  `recall@5` on the benchmark corpus is 0.96 with the model against 0.93 with the
  hashing fallback. Retrieval changes can now be evaluated instead of argued about.
- Harder: install is ~240 MB heavier and first run needs network. Constrained
  environments (CI images, containers, air-gapped hosts) must set
  `DOCIR_EMBEDDER=deterministic` — a documented, tested path, not a degraded
  accident.
- The test suite pins `DOCIR_EMBEDDER=deterministic` in its fixtures, so it stays
  hermetic and model-free; only the `slow` embedder tests load the model.
- Switching embedders in either direction re-embeds rather than failing, but the
  first read after a switch has no semantic signal until the recompute runs.
- Follow-up: the benchmark's relevance judgments are single-annotator and its
  corpus is synthetic (limits are listed in `benchmarks/README.md`). Nothing yet
  measures whether retrieved context changed what an agent actually did, which is
  the outcome the product exists for.

## The measurement, and the instrument it needs

The corpus is **23 documents / 14 tasks**. It was re-based from 20/12 because the
original had no `supersedes` edge and no document in an inactive status, so the two
graph behaviours `docir context` depends on most were unmeasurable — two fixes that
changed retrieval semantics moved no number at all. A superseded decision pair and a
closed issue made them visible.

| | hashing embedder | real model |
|---|---|---|
| `context` | 0.93 (MRR 0.80) | **0.96 (MRR 0.95)** |
| `context --expand 0` | 0.80 | **0.87** |
| `search` (lexical only) | 0.83 (MRR 0.82) | 0.83 (MRR 0.82) |

**Quote the `--expand 0` pair, not full `context`.** Full `context` separates the
embedders by 0.03, because it bundles the ranking with a graph traversal that has
nothing to do with them and expansion lifts both equally. Read alone that looks like
a case for reverting. `--expand 0` isolates the ranking, and there the hashing
embedder scores **0.80 recall / 0.80 MRR against plain `search`'s 0.83 / 0.82** — it
ranks *below* the lexical index it is supposed to be complementing, because it
measures the same signal with less precision. The model scores 0.87 / 0.95.

So "the hashing embedder bought noise" was if anything too generous: on the better
instrument it is a small net negative.

## Re-basing a benchmark can invalidate the argument it was built to support

The general lesson, since it will recur. When the corpus moves, re-derive the
argument on the new instrument rather than keeping the corpus that flattered the
conclusion — and say so wherever the old numbers are still printed, because a reader
comparing across a silent re-base draws a conclusion about code from a change in the
denominator.
