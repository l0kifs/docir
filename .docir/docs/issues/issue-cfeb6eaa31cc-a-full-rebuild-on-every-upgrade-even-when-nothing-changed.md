---
code:
- src/docir/modules/documents/application/services/maintenance_service.py
- src/docir/entry_points/composition.py
- src/docir/entry_points/dispatch.py
created: '2026-08-16'
description: 'docir self upgrade ran an unconditional full reindex, and 96% of that
  is re-embedding: 58.4s of 60s on a 315-document store whose files had not moved.'
id: issue-cfeb6eaa31cc
owner: maintainer
related:
- kind: refines
  to: adr-6a4718fa7a7d
- kind: refines
  to: adr-31aa7aa60d11
- issue-9509f9fa3631
- ref-e7534f1c812d
status: resolved
tags:
- cli
- embeddings
- release
- material
title: A full rebuild on every upgrade, even when nothing changed
type: issue
updated: '2026-08-16'
---

## What was measured

Every command in the CLI, timed as a whole `python -m docir` process against a copy of a
real 315-document store (1,326 vectors: 315 document + 1,011 section). Apple M1, docir
0.15.0, `--no-daemon`, output captured so each one takes the JSON path an agent takes.

This is the half `benchmarks/latency.py` never covered. That harness times `context`,
`search` and `get`, and concluded the read path is fast and interpreter startup dominates
— both still true. Nothing measured the write and maintenance path, which is where a
command that takes a minute was sitting unreported.

## Numbers

p50 seconds, `--no-daemon`, 313–315 documents.

| command | s | command | s |
|---|---|---|---|
| `docir check --fix` | 59.8 | `docir add` / `docir update` | 1.2–1.6 |
| `docir reindex` | 58.5 | `docir check` | 0.97 |
| `docir build` | 4.3 | `docir archive` / `docir delete` | ~0.7 |
| `docir lint --deep` | 2.4 | `docir version` (floor) | 0.5 |
| `docir query` / `search` / `get` / `context` | 1.3–1.7 | | |

Two outliers, and the second is the first: `check --fix` reindexes before allocating ids.
Everything else is at or under 4.3 s.

## Where the 58 seconds goes

Embedding, and nothing else. The same rebuild against the model-free hashing embedder
(`DOCIR_EMBEDDER=deterministic`) costs 2.5 s, so the model accounts for 96%.

| run | time |
|---|---|
| full rebuild, real model | 58.4 s |
| full rebuild, hashing embedder | 2.5 s |
| `docir reindex --changed`, nothing moved | 1.5 s |

The 1.5 s row is the point: the work was already skippable, and the flag that skips it
already shipped.

## Why an unchanged corpus paid for it

`docir self upgrade` ran an unconditional full reindex — including the run that reports
"already the newest build", where no package moved and no file changed. A full rebuild
re-embeds every document it re-saves, so all 1,326 vectors were recomputed
byte-identical to the ones already stored.

`docir check --fix` paid it twice: its repair reindexes in full before allocating ids,
and again after re-issuing duplicates.

## The fix

`MaintenanceService.resync` reads the index build stamp *before* rebuilding — both modes
write it, so a cheap pass would erase the evidence a full one was needed — and takes the
changed-only path only when the stamp equals the running version. A genuine version move
still rebuilds in full, which is what adr-6a4718fa7a7d reserves it for.

It compares equality rather than reusing `stale_index_build()`, which folds "never
recorded" into absent so `docir check` stays quiet. Here unknown has to mean rebuild: a
store with no stamp was last built by code that did not write one.

Repair's two rebuilds are now changed-only. Agreeing with the files is all either is for.

## Measured after

| case | before | after |
|---|---|---|
| `docir self upgrade`, stamp equal | 65 s | 1.5 s |
| `docir self upgrade`, stamp moved | 65 s | 62 s |
| `docir reindex` | 64 s | 64 s |

## Batching and thread tuning were measured and rejected

The obvious next move — feed the model a batch instead of one text per call — makes it
slower on this hardware, because onnxruntime already saturates the cores on a single
~300-token sequence and fastembed pads every batch to its longest member.

| config | ms/text |
|---|---|
| shipped default, one text per call | 58.2 |
| batch 16, length-sorted | 79.3 |
| batch 64, length-sorted | 100.3 |
| 4 threads | 66.1 |
| 8 threads | 101.4 |

Do not retry either without a fresh measurement on different hardware.

## What not to conclude

That embedding got cheaper. It did not: a real version move still costs ~62 s per 315
documents, and that is the floor for a release that changes how documents are read. The
only win available was not embedding what did not change.

Nor that the daemon helps here. It keeps the model warm, which is worth ~0.5 s against a
58 s command — the observed 65 s through a warm daemon and 58.5 s in-process are the same
number on a different day.
