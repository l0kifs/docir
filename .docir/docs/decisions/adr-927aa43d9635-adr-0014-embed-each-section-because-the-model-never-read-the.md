---
created: '2026-08-03'
description: 'Why per-section vectors exist: 56% of the corpus was outside the model''s
  token window and absent from the semantic index.'
id: adr-927aa43d9635
owner: maintainer
related:
- kind: refines
  to: adr-ab9c454b760c
- arch-f220a644d654
status: accepted
tags:
- architecture
- embeddings
- retrieval
title: 'ADR-0014: Embed each section, because the model never read the rest'
type: decision
updated: '2026-08-03'
---

# ADR-0014: Embed each section, because the model never read the rest

Status: accepted
Date: 2026-08-03

## Context
docir's semantic index made a claim it did not honour. `bge-small-en-v1.5`
reads about 512 tokens and silently ignores everything after them — not
downweights, ignores. Appending a sentence past that point returns a
bit-identical vector, cosine 1.000000.

Measured on this project's own prose the window is about **1,900 characters**.
docir's own store has 103 documents; **84 exceed it**. Corpus-wide, **44% of the
text was inside a vector and 56% was not in the semantic index at all**. The
architecture document (28,546 chars) had 8% of itself embedded; the business
rule register (36,981) had 5%. Those tails were not ranked badly. They were
absent, and nothing anywhere said so — `docir context` returned a plausible
answer every time.

Full-text search hid it. FTS5 indexes the whole body, so any query sharing
vocabulary with a document found it and RRF pulled it to rank 1 regardless of
whether the vector had seen the relevant part. The failure was visible only on
paraphrased queries against long documents, which is precisely the case
`docir context` exists for and the case ADR-0011 justified the model with.

## Decision
Embed **each section separately**, in addition to the document vector.

- **The split rule** (`documents/domain/services/chunking.py`): cut at `##` and
  deeper; `#` is the title restated in the body, not a boundary. Text before the
  first heading is chunk 0, so a document with no headings is exactly one chunk.
  Never split inside a fenced code block — a `##` comment in a Python block is
  not a heading, and cutting there yields two chunks that are each invalid
  markdown. Sections under 200 characters merge forward; sections over 1,200 are
  split on paragraph boundaries. **1,200 is derived from the measured window, not
  chosen**: each chunk is prefixed with the document title, and a chunk that
  overflows the window reintroduces the bug one level down.
- **Each chunk carries the title.** A section read alone often never restates
  its subject — "Rotation is a runbook step" names neither certificates nor the
  provider — so without the prefix it cannot answer a query phrased in the
  document's terms, which is how people ask.
- **Storage is a new `chunk_embeddings` table** keyed `(doc_id, ordinal)`,
  cascading from `documents` (migration `0003`). The document vector stays
  exactly as it was. There is no second dirty flag: a chunk set is derived from
  a body, so it is invalidated by the same thing that invalidates the document
  vector, and both are rewritten in one transaction under the existing queue.
- **Ranking pools chunks to documents before fusion.** `HybridScorer.
  semantic_ranking` now accepts repeated ids and keeps each document's best.
  RRF fuses two rankings *of documents*, so the collapse has to happen before
  it. Max rather than mean: a document is relevant when *some* part of it
  answers, and averaging in five sections about something else is the dilution
  being undone. FTS5 is untouched — chunking the lexical side too would have
  made `score` describe sections and changed what `--min-score` means.
- **`get --section` is the paired read.** Chunking lets `context` rank a
  document on one section; without a way to read that section the follow-up is
  still a 28,000-character body. `get --section X` returns exactly the span
  `update --replace-section X` would overwrite — one notion of where a section
  ends, so an agent cannot read one span and overwrite another. An unknown
  heading errors *listing the real ones*, because discovering them by fetching
  the whole body is the cost this path exists to remove.

## Consequences
- **Coverage went from 44% to 100%** on docir's own store: 695 chunks for 103
  documents. That is the headline metric, and it is deliberately not recall.
- **Recall did not regress and ranking improved.** Same corpus, chunking off vs
  on: `context` recall@5 0.97 → 0.97, **MRR 0.94 → 0.97**. The no-regression
  gate matters because max-pooling structurally favours documents with more
  sections — more chances to score. It is checked, not assumed.
- **Recall could not have proven this and was not asked to.** On a 26-document
  benchmark FTS5 finds the tail and rescues the rank, so the corpus shows 87% →
  94% coverage and almost no recall movement. Growing that corpus until a delta
  appeared would have meant authoring the exam being graded. `benchmarks/run.py`
  now reports coverage, measuring the window empirically rather than hardcoding
  it.
- **Roughly 7x more vectors.** 103 documents became 695 rows, and `context`
  loads every active vector per call. That lowers the practical corpus ceiling,
  which was already set by the same behaviour, by about the same factor. It is
  the cost of the fix, not a surprise.
- **Existing stores recompute.** Migration `0003` marks every embedding dirty,
  because a store whose vectors already match the current `model_id` is never
  stale and would otherwise upgrade to zero chunks — a no-op on exactly the
  corpora that need it. The refill happens on the next write or `docir embed
  --flush`, the same eventual-consistency contract every embedding change has.
- **`lint --deep` still compares document vectors only.** The duplicate check
  asks whether two documents are the same document; chunk vectors would answer
  whether they share a section, which is a different and far noisier question.
- **The premise is now a test.** `test_chunked_retrieval.py` asserts the model
  truncates before asserting anything else, so if a future model reads whole
  documents this decision is revisited rather than quietly obsolete.
