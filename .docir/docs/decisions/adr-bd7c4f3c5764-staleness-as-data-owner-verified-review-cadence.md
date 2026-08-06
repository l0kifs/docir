---
code:
- src/docir/modules/documents/domain/services/graph_checks.py
created: '2026-07-23'
description: Why staleness is owner + verified + review cadence data rather than a
  heuristic.
id: adr-bd7c4f3c5764
owner: maintainer
related:
- kind: refines
  to: arch-1cfb1b212237
status: accepted
tags:
- staleness
- schema
title: Staleness as data (owner + verified + review cadence)
type: decision
updated: '2026-08-06'
---

## Context
Read-only doc systems drift; docir's write path keeps docs *consistent* but says
nothing about whether they are still *true*. `created`/`updated` track edits, not
confirmations — a doc nobody has touched in a year is indistinguishable from one
verified yesterday. There was no honest signal for "this needs a human to
re-check it".

## Decision
Model staleness explicitly, as data rather than a heuristic:
- Two optional frontmatter fields: `owner` (a steward) and `verified` (the date a
  human last confirmed the doc is still correct). Both are `NULL`/empty by
  default and written only when set, so untyped/unowned docs keep clean
  frontmatter. Persisted as `documents.owner` / `documents.verified` (migration
  `0002`).
- A per-type `review_days` cadence in the schema. A doc is stale when
  `today - (verified or updated) > review_days`; `review_days: 0` means the type
  is never stale.
- Surfacing is **Tier 1** (non-blocking `docir check`, a `stale` finding) plus a
  computed `stale` flag on every read view. Stamp the clock with
  `docir update <id> --verified`; set the steward with `--set-owner`.

This keeps the three-tier discipline (§ validation): staleness is a graph-level
warning, never a write-blocking Tier 0 error and never a Tier 2 guess.

## Consequences
- Easier: an honest, explicit re-verification mechanism for *any* doc type,
  dev or not; owners are accountable; CI can surface overdue docs.
- Scoped out: **AST-anchored** staleness for code-backed docs (tie a doc to code
  symbols and flag it when they change) is deliberately **not** implemented here.
  It needs a code-analysis subsystem and a language-aware anchor format; doing it
  half-way would violate "never promote a heuristic to a hard error". Human
  re-verification is the honest baseline; AST anchoring is a future, additive
  layer that can set `verified` automatically without changing this model.
