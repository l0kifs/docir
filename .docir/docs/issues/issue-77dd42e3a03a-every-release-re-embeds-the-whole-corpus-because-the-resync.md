---
code:
- src/docir/modules/indexing/infra/scheduler.py
- src/docir/modules/documents/application/services/index_rebuilder.py
- src/docir/platform/persistence/alembic/versions/0012_embedding_input_digest.py
code_baseline:
  src/docir/modules/documents/application/services/index_rebuilder.py: fbb0bff13bc4
  src/docir/modules/indexing/infra/scheduler.py: 3cc2831c6de3
  src/docir/platform/persistence/alembic/versions/0012_embedding_input_digest.py: fd1cdd2ec6ba
created: '2026-09-06'
description: '`resync` keys the full rebuild on docir''s version, so a release that
  changed neither the model nor the chunking still recomputes every vector — 58.4s
  against 1.5s on this repository.'
id: issue-77dd42e3a03a
owner: maintainer
related:
- adr-31aa7aa60d11
- adr-56d29d521620
status: resolved
tags:
- daemon
- embeddings
- material
title: Every release re-embeds the whole corpus, because the resync stamp is the version
type: issue
updated: '2026-09-17'
verified: '2026-09-17'
verified_code:
  src/docir/modules/documents/application/services/index_rebuilder.py: fbb0bff13bc4
  src/docir/modules/indexing/infra/scheduler.py: 3cc2831c6de3
  src/docir/platform/persistence/alembic/versions/0012_embedding_input_digest.py: fd1cdd2ec6ba
verified_content: 052e2947dd8a
---

## What happened

A full rebuild re-saves every document, which marks every one dirty, and the
drain then recomputed every vector. So every release re-embedded the whole
corpus: 1,547 vectors and 146s against this repository's 205 documents, on a
release that had changed neither the model nor the chunking.

`MaintenanceService.resync` keyed the decision on the docir *version*, which is
unequal on every release — including the ones that touch neither.

## Why a version stamp was the wrong key

The vectors need recomputing when the *embedding contract* moved: the model id,
or how a document is split into chunks (adr-6a4718fa7a7d). A second stamp
holding that contract would have worked and carried one failure mode — a
chunking change that forgets to bump the constant produces vectors that
silently describe the old splitting, and no test can catch that.

## How it was fixed

The vectors are keyed on their own inputs instead, so nothing has to be
remembered. `embeddings.input_digest` (migration `0012`) hashes the model id,
the document's `embedding_text()` and every `embedding_chunks()` triple;
`drain_dirty` compares it and, on a match, clears the dirty flag and embeds
nothing. Content, model and chunking are each covered by construction — a
different splitting is a different set of triples and so a different digest.

Two details are load-bearing:

- `None` means *unknown*, never *unchanged*. A row written before `0012` has
  vectors and no record of what produced them, so the first drain after the
  upgrade recomputes it. That is the state every adopter starts from.
- The digest alone is not enough. Chunks live in their own table and are
  dropped by their own calls, so a document whose chunk rows were removed still
  carries a matching digest and would be skipped forever — `reindex` would stop
  being the repair for it. The skip also requires the stored chunk count to
  match what the document would produce. The existing
  `test_reindex_rebuilds_chunks_from_the_files` is what caught this.

The build stamp still governs the *metadata* pass, which is what it was
always actually answering: a release can change how a document is read without
changing the document.

## Result

`docir self upgrade --no-package` against this repository, version stamp moved
and nothing else: **146s → 2.6s**, 205 documents re-read, 0 vectors recomputed.
A single hand-edited document still reports exactly one re-embed.

## Related

Deferred out of adr-56d29d521620, which fixed the *timeout* this cost was
hitting.
