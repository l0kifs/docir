---
created: '2026-07-30'
description: A typo in `FastEmbedEmbedder.embed` would have shipped green to every
  default install.
id: issue-0ff355fa21dd
owner: maintainer
related:
- adr-ab9c454b760c
- arch-f220a644d654
status: resolved
tags:
- embeddings
- material
title: The default embedder path was excluded from every quality gate
type: issue
updated: '2026-08-05'
---

**Class:** unstated · **Severity:** material
**Flow:** arch-f220a644d654 · **Step:** the gates, once fastembed became the default
**Question:** None · **Frequency:** every CI run since the default flip

## Finding

The default embedder path was excluded from every quality gate. `fastembed.py` was excluded from `ty`, omitted from coverage, carried `# pragma: no cover`, and no test referenced it — while CI installed ~240 MB of dependencies and then exercised none of it.

## What happens today

FOUND AND FIXED 2026-07-27, immediately after the default flip. The exclusions were written when the adapter was opt-in, where they were defensible; making it the default silently turned them into a hole. Their own comments had become false ("imports an optional, not-installed dependency"). Lifting the `ty` exclusion surfaced a real diagnostic on the first run: `unresolved-attribute: Object of type object has no attribute embed` — the adapter held its model as a bare `object` behind a mypy-flavoured `type: ignore`.

## Impact

A typo in `FastEmbedEmbedder.embed` would have shipped green to every default install. The general shape is worth remembering: an exclusion is scoped to an assumption ("optional, rarely used"), and nothing re-checks the exclusion when the assumption changes.

## Proposed default

FIXED. Both exclusions dropped; the adapter now depends on a `_TextEmbedding` Protocol instead of `object`, so it type-checks honestly. Three `slow` tests exercise the real model (dimension, meaning-over-wording, determinism) plus fast tests for embedder selection and the missing-dependency fallback. Coverage of the file went from omitted to 97%. CI caches `~/.cache/fastembed` so the ~64 MB download happens once, not per run. `pytest -m "not slow"` still runs model-free for local work.

## Actors affected

- repository maintainer
- AI coding agent

## Evidence

- `pyproject.toml`
- `.github/workflows/ci.yml`
- `src/docir/platform/embedding/fastembed.py`

---

Migrated from the discovery gap register (GAP-045); the register itself now lives in this store.
