---
code:
- src/docir/platform/embedding/**
- src/docir/modules/documents/domain/schema.py
created: '2026-08-15'
description: What the default embedder costs to install, what the model-free fallback
  loses, and how a store names a different model.
id: ref-e7534f1c812d
owner: maintainer
related:
- adr-ab9c454b760c
- adr-927aa43d9635
status: active
tags:
- embeddings
- retrieval
title: 'The embedding model: what it costs, and what the fallback loses'
type: reference
updated: '2026-08-25'
---

Semantic search runs on a real embedding model, installed by default. It is quantized,
CPU-only, and runs locally — nothing is sent anywhere — but it is not free, and the
fallback is not equivalent. This is what each costs.

## What ships by default

| | |
|---|---|
| Model | `BAAI/bge-small-en-v1.5`, 384-dim, quantized ONNX |
| Download | **~64 MB**, once, on first use — the only step that needs network |
| Install | **~240 MB** of dependencies (`onnxruntime`, `numpy`, `tokenizers`, …) |
| Runtime | CPU only, no GPU, no API key; the daemon keeps the model warm |
| Window | ~512 tokens (~1,900 chars) — which is why docir embeds per section, below |

## Opting out, and what it costs

If that is too heavy — a CI image, a container you keep small, an air-gapped box —
set the environment variable and docir falls back to a dependency-free hashing
embedder:

```bash
export DOCIR_EMBEDDER=deterministic
```

That embedder scores similarity by *shared vocabulary* rather than meaning, which is
the same signal the full-text index already provides. The cost is measured, not
asserted: `docir context` scores **recall@5 0.97 (MRR 0.97)** with the model against
**0.80 (MRR 0.76)** without it.

The gap is entirely in how a question is phrased. On tasks worded in the documents' own
vocabulary both reach 0.95+. On tasks sharing *no* words with the document they need,
the model holds **0.95** where the fallback collapses to **0.65**.

Isolate the ranking by turning graph expansion off (`--expand 0`) and the fallback does
not merely add nothing: at **0.78** it ranks *below* the **0.86** that plain full-text
search manages on its own, while the model reaches 0.88. Paying for a vector index that
loses to your lexical one is the case for making the model the default.

Quote the `--expand 0` pair when arguing about embedders — full `context` numbers
include graph expansion, which lifts both and hides the difference.

Corpus, tasks, judgments and caveats are in
[`benchmarks/`](https://github.com/l0kifs/docir/tree/main/benchmarks);
`uv run python benchmarks/run.py` reproduces the figures.

## Long documents are embedded per section

The model reads about 512 tokens — roughly 1,900 characters — and silently ignores the
rest. Not downweights: ignores. Append a sentence past that point and the vector comes
back bit-identical.

84 of the 103 documents in docir's own store were longer than that, so **56% of the
corpus was not in the semantic index at all** — and nothing said so, because full-text
search covers the whole body and rescued the rank on any query that shared a word with
the document.

docir therefore embeds **each `##` section as well as the whole document**, and a
document ranks on its best-matching section. Coverage on docir's own store went
**44% → 100%**. On the same corpus, `context` recall@5 holds at 0.97 while MRR rises
0.94 → 0.97. `benchmarks/run.py` reports the coverage figure and measures the window
empirically, so it stays honest if the model changes.

## Reading follows ranking

If `context` surfaced a document for one of its sections, the hit says which —
`matched_section` carries that heading, ready to read back:

```bash
docir get arch-1cfb1b212237 --section "Daemon process"
```

It returns the same span `update --replace-section` would overwrite, and an unknown
heading errors listing the ones that exist. An absent `matched_section` means the hit
is not addressable as a section — the document's own vector won, or the match was
lexical or graph-reached — never that nothing matched.

## Switching embedders re-embeds rather than mixing vector spaces

docir records which model produced each vector, ignores the ones a different model
wrote, and recomputes them on the next write or on `docir embed --flush`. Different
models have different widths, so the alternative is a dimension-mismatch error on every
read in an existing store. The first read after a switch has no semantic signal until
the recompute lands.

## Choosing a different model

The default is `bge-small-en-v1.5`, and since 0.18.0 it is a **default rather than the only
option**. A store names another with a top-level `embed_model:` key in `docs-schema.yaml`.

This matters most for a corpus not written in English, where the default is not merely weaker —
it is worse than turning semantic search off. Measured on a Russian translation of the
benchmark corpus, same documents and same judgments so language is the only variable:

| corpus | model | recall@5 | MRR | paraphrased |
|---|---|---|---|---|
| Russian | `bge-small-en-v1.5` | 0.75 | 0.63 | **0.50** |
| Russian | `paraphrase-multilingual-MiniLM-L12-v2` | 0.86 | 0.90 | **0.80** |

The default's perfect 1.00 on same-words tasks beside a paraphrased 0.50 is FTS5 carrying the
whole lexical half unaided — which is what "no better than full-text search" means as a number.

On the **English** corpus the same swap costs ranking and buys nothing, which is why the default
does not move. Both halves of the design are evidenced, by different rows.

Any model `fastembed` supports is accepted; three are measured. Anything else is accepted with a
warning, because docir embeds queries and documents through the same call, so a model trained on
asymmetric `query:`/`passage:` prefixes ranks below its published numbers. `docir self status`
reports the model in force, and switching re-embeds rather than mixing vector spaces — see
below. (adr-ab9c454b760c built that machinery; the setting is what it was missing.)
