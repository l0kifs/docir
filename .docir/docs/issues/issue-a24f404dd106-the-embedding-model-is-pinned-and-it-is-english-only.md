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
status: resolved
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

## What it buys a Russian corpus, measured

`benchmarks/multilingual.py`, 2026-08-24 — the same 26 documents and 20 tasks as `run.py`,
translated. `multilingual_corpus.yaml` keeps identical keys, edges and judgments, so the
English run is the control and language is the only variable. Two runs, byte-identical.

| corpus | model | recall@5 | MRR | same words | paraphrased |
|---|---|---|---|---|---|
| English | `bge-small-en` | 0.97 | 0.97 | 1.00 | 0.95 |
| English | multilingual | 0.95 | 0.91 | 0.95 | 0.95 |
| Russian | `bge-small-en` | 0.75 | 0.63 | 1.00 | **0.50** |
| Russian | multilingual | 0.86 | 0.90 | 0.92 | **0.80** |

## Why those two rows settle it

The paraphrased column decides: a lexical task shares vocabulary with the documents, so FTS5
carries it in either language and the embedder is not what is being measured.

The Russian default row **is** this issue's opening claim in numbers. Same-words recall of a
perfect 1.00 — FTS5 doing the whole lexical half unaided — beside a paraphrased 0.50. That gap
is "retrieves no better than full-text search", visible for the first time. The multilingual
model closes it to 0.80, and MRR with it, 0.63 -> 0.90.

Both halves of the shipped design are now evidenced, by different numbers: the *setting* by the
Russian rows, the *unchanged default* by the English ones, where the same swap costs ranking
and buys nothing.

## What shipped, and what did not

Shipped in `695a794` — three of the four, and none of them needed the machinery above.

1. ~~**A setting.**~~ A top-level `embed_model:` key in `docs-schema.yaml`, beside `id_style`,
   which is the precedent: a store-wide policy that is not a type concept. It lives in the
   committed file rather than an environment variable because the index is gitignored — two
   clones holding different models would each re-embed the corpus behind the other.
2. ~~**Nothing surfaces the active model.**~~ `docir self status` reports it, resolved rather
   than requested: `active_embedder_id` calls `_build_embedder`, so status cannot name a model
   the reads do not use.
3. ~~**A bad name fails late and quietly.**~~ `verify_embed_model` runs where the embedder is
   built and where `schema validate` runs, so a name nothing supports exits 3 at command time.
4. **`Embedder.dimension` is consumed nowhere** outside the embedding package, and fastembed
   exposes `get_embedding_size()`, so the self-correcting `_dimension` field is still dead
   weight. Untouched: removing it is a port change, and nothing depends on the answer.

## Not every model is a drop-in

`Embedder.embed(text)` is symmetric: `document_service` embeds the query through the same call
that embedded the documents. For the default that is correct — measured, not assumed:
`query_embed` and `embed` return a bit-identical vector for `bge-small-en-v1.5`, because
fastembed's base `query_embed` is a passthrough and only its multitask class overrides it.

It stops being correct elsewhere. E5 is trained on `query: ` / `passage: ` prefixes that neither
docir nor fastembed applies, and `jina-embeddings-v3` selects a task-specific adapter through
`query_embed`/`passage_embed`, which docir never calls. Both load, embed, and score below their
published numbers.

**Resolved as a warning rather than an exclusion**, which was neither option this section
originally posed. Refusing them would have made the catalogue a gate, and a hardcoded tuple is
worse placed to choose a model than somebody writing in a language docir has never benchmarked.
So a model fastembed supports is accepted, with one line saying what it may cost, and only a
name nothing supports is refused. Growing the port a role-aware call stays open and is now
optional rather than blocking.

## What was decided

All three questions this section carried are answered.

- **Where the setting lives** — `docs-schema.yaml`, top-level, beside `id_style`.
- **Whether the port grows a role-aware call** — neither of the two options posed. See
  *Not every model is a drop-in*: warn, do not refuse. The port change is optional now.
- **Whether an unknown name is refused** — yes, but only a name *fastembed* does not know.
  A name it knows and docir has not measured is accepted with a warning, so
  `add_custom_model` and any of fastembed's other models stay reachable.

## What is left

Nothing this issue was opened for. It existed because a non-English corpus retrieved no better
than full-text search with nothing to report it. A store can now name a model, the model
measurably helps, and `docir self status` reports which one is in force.

One item that was never central to it moved to its own issue: `Embedder.dimension` is declared
on the port and read nowhere outside the embedding package — issue-6618d3a9e868. A cleanup, not
a defect, and nothing depends on the answer.

The constraint in *Not every model is a drop-in* is documentation rather than debt — a model
needing asymmetric prefixes is accepted with a warning naming what it costs. Growing the port a
role-aware call would admit those models properly, and nothing measured here requires it.
