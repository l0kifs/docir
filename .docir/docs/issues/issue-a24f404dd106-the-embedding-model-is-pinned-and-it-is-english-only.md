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
- adr-ab9c454b760c
- ref-a6db21f52427
- ref-e7534f1c812d
- issue-c6d184704682
- issue-fd086c0c6ab0
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

Surveyed 2026-08-24 against fastembed 0.8.0, and the answer is: most of it is already built,
because adr-ab9c454b760c had to build it to survive a *change* of embedder.

`FastEmbedEmbedder.__init__` already takes a `model_name` — nothing has ever passed one.
`model_id` is already `fastembed:<name>`, so two models cannot share a vector namespace.
`Embedding.to_bytes`/`from_bytes` are width-agnostic and the columns are BLOBs, so a
different dimension needs no migration. `dirty_ids(model_id)` treats a foreign or NULL id as
dirty and `active_vectors(model_id)` filters, for document *and* chunk vectors — so a switch
recomputes on the next write or `embed --flush` rather than raising.

What is missing is the setting that would let anyone pass a name, and the guard rails around it.

## What a replacement model costs

fastembed 0.8.0 supports 30 models. The four that matter here, against the current default:

| model | dim | download |
|---|---|---|
| `BAAI/bge-small-en-v1.5` (current) | 384 | 67 MB |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 384 | 220 MB |
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | 768 | 1.0 GB |
| `intfloat/multilingual-e5-large` | 1024 | 2.24 GB |

The first alternative is a true drop-in — same 384 width, +153 MB, symmetric. `BAAI/bge-m3` is
not in the supported set. Gap 10 of ref-a6db21f52427 says install weight and ranking quality are
one decision rather than two, and this table is that decision priced.

## What the drop-in costs, measured

`benchmarks/run.py`, 2026-08-24, fastembed 0.8.0 — 26 documents, 20 tasks. Two runs per model,
byte-identical output, so the deltas are not run-to-run noise.

| metric | `bge-small-en-v1.5` | `paraphrase-multilingual-MiniLM-L12-v2` |
|---|---|---|
| `context` recall@5 | 0.97 | 0.95 |
| `context` MRR | 0.97 | 0.91 |
| `context --expand 0` recall@5 | 0.88 | 0.88 |
| paraphrased recall@5 | 0.95 | 0.95 |
| same-words recall@5 | 1.00 | 0.95 |

The two figures that isolate the embedding signal — `--expand 0` and the paraphrased split —
are **identical**. The multilingual model is not worse at meaning on this corpus. What it loses
is ordering, and one *same-words* task, which is the lexically easy case an English-specialised
model should win. So the default does not move, and the deliverable is the setting rather than
a swap.

Two caveats bind these numbers. The corpus is English, so it cannot measure the thing the model
exists for — issue-c6d184704682 in miniature, and the reason a non-English fixture is the next
measurement rather than a nicety. And fastembed 0.8.0 warns this model moved from CLS to mean
pooling since 0.5.1, so the figures are bound to that version.

## What is still missing

1. **A setting.** `Settings` is pydantic-settings with `env_prefix="DOCIR_"`, so a field would
   pick up an env var for free — but `_build_embedder()` takes no `Settings` and reads
   `os.environ` directly.
2. **Nothing surfaces the active model.** `self status` does not report it, so a switch cannot
   be confirmed and the current state cannot be read.
3. **A bad name fails late and quietly.** `TextEmbedding(...)` raises on first use, which is
   inside the scheduler thread, where `DocsWatcher._reindex` swallows failures on purpose. A
   typo therefore yields a daemon that looks healthy and has stopped embedding.
4. **`Embedder.dimension` is consumed nowhere** outside the embedding package, and fastembed
   exposes `get_embedding_size()`, so the self-correcting `_dimension` field is dead weight.

## Not every model is a drop-in

`Embedder.embed(text)` is symmetric: `document_service` embeds the query through the same call
that embedded the documents. For the shipped model that is correct — measured, not assumed:
`query_embed` and `embed` return a bit-identical vector for `bge-small-en-v1.5`, because
fastembed's base `query_embed` is a passthrough and only its multitask class overrides it.

It stops being correct for two of the multilingual candidates. E5 is trained on `query: ` /
`passage: ` prefixes that neither docir nor fastembed applies, and `jina-embeddings-v3` selects
a task-specific adapter through `query_embed`/`passage_embed`, which docir never calls. Both
would load, embed, and silently score below their published numbers.

So the selector cannot be a bare model name for exactly the models this issue exists to enable.
Either the port grows a role-aware call, or the setting is restricted to the symmetric models —
which the drop-in above happens to be.

## What is not decided

Narrowed by the survey, then by the measurement — which settled the fourth of these: the
default does not move.

- **Where the setting lives.** A `docs-schema.yaml` key is committed and travels with the
  corpus, which matters because the index is gitignored: with a per-machine env var two clones
  can hold different models, and each re-embeds the whole corpus whenever the other's value is
  in effect. The cost is that a model change would surface as `schema-drift` — the right
  *mechanism* under a name that does not describe it.
- **Whether the port grows a role-aware call** (`embed_query` beside `embed`) or the supported
  set is restricted to symmetric models. The first is general and touches every implementation
  of the port. The second ships the drop-in and defers the rest.
- **Whether an unknown model name is refused at construction** — checkable against
  `list_supported_models()` — or accepted on trust so `add_custom_model` stays reachable.
