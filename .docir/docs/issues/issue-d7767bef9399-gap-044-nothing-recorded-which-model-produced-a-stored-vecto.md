---
created: '2026-07-30'
description: A dead column that turned out to be load-bearing.
id: issue-d7767bef9399
owner: maintainer
related:
- adr-ab9c454b760c
- arch-f220a644d654
status: resolved
tags:
- embeddings
- material
title: GAP-044 — Nothing recorded which model produced a stored vector, so changing
  embedder left the…
type: issue
updated: '2026-07-30'
---

# GAP-044 — Nothing recorded which model produced a stored vector, so changing embedder left the…

**Class:** unstated · **Severity:** material · **Confidence:** observed
**Flow:** FLOW-002 · **Step:** changing the embedder on an existing store
**Question:** None · **Frequency:** every store upgrading past the default flip

## Finding

Nothing recorded which model produced a stored vector, so changing embedder left the index full of vectors from the old one. Different models have different widths, and `Embedding.cosine_similarity` raises on a mismatch rather than degrading.

## What happens today

FOUND AND FIXED 2026-07-26 while making fastembed the default — the change would have broken every existing store on upgrade. Verified before the fix: `Embedding((0.1,)*256).cosine_similarity(Embedding((0.1,)*384))` raises `ValueError: dimension mismatch: 256 != 384`, and `docir context` reads every active vector, so the first read after upgrading would have raised. The `embeddings.model_id` column existed since migration 0001 but `set_vector` never wrote it, so there was no way to detect the switch either.

## Impact

A dead column that turned out to be load-bearing. Any embedder change — the new default, a future model upgrade, or a user toggling DOCIR_EMBEDDER — would have made the flagship read path raise until someone guessed at `docir reindex --embeddings`.

## Proposed default

FIXED. `set_vector` writes `model_id`; `active_vectors(model_id)` returns only matching rows so foreign vectors fall out of ranking instead of raising; `dirty_ids(model_id)` treats a foreign or NULL model_id as dirty, so they are recomputed on the next write or `docir embed --flush`. Verified end to end: a store built with the old embedder now answers `docir context` without error after the switch and re-embeds transparently. Pinned by test_vectors_from_another_model_are_recomputed_not_compared. Residual: the first read after a switch has no semantic signal until the recompute runs.

## Actors affected

- AI coding agent
- repository maintainer

## Evidence

- `src/docir/platform/persistence/repositories.py:272-300`
- `src/docir/platform/embedding/vector.py`
- `src/docir/platform/persistence/alembic/versions/0001_initial_index.py:69-80`

---

Migrated from the discovery gap register (GAP-044); the register itself now lives in this store.
