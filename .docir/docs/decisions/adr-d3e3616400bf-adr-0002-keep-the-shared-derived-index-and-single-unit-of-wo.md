---
created: '2026-07-22'
description: Why one shared SQLite schema and unit-of-work spans all contexts, and
  what that costs.
id: adr-d3e3616400bf
owner: maintainer
related:
- kind: contradicts
  to: arch-322e5f992ad2
status: accepted
tags:
- architecture
- persistence
title: 'ADR-0002: Keep the shared derived index and single unit-of-work'
type: decision
updated: '2026-07-30'
---

# ADR-0002: Keep the shared derived index and single unit-of-work
Status: accepted
Date: 2026-07-22

## Context
`docir` compiles markdown into one derived SQLite index (metadata + FTS5 +
relation graph + embeddings) plus the canonical files, and mutates them in a
single unit-of-work so a write and its index update are atomic. A strict reading
of ARCHITECTURE_RULES §5.1/§5.3 forbids sharing a transaction across modules and
requires each table to have exactly one owning module. Fully honoring that would
mean per-module storage and event-driven, eventually-consistent cross-module
consistency — a large rewrite of working, tested software with real regression
risk, for a single-user local tool where the atomic write is a feature.

## Decision
Keep the single shared SQLite schema, the shared `UnitOfWork`, and the shared
file stores. House them in `platform/persistence` and `platform/filesystem`.
Because their repositories and stores map each context's domain entities, they
depend on `modules/<context>/domain`. Declare exactly these edges in `tach.toml`
as `deprecated = true`: they are the initial ratchet baseline (§8.1, §12.1),
reported on every run and allowed only to shrink. Modules never share a
transaction through each other's code — all shared-data access goes through
`platform`, which keeps the module graph acyclic (`tags → documents → indexing`).

## Consequences
- Easier: atomic writes; a small, well-understood persistence layer; no event
  bus or idempotency machinery to maintain.
- Harder: `platform` is not a pure leaf; the baseline edges must be watched so
  they do not grow.
- Now forbidden (by the ratchet): any NEW `platform → module` edge, or any new
  cross-module transaction coupling. Shrinking the baseline — by splitting the
  index per module behind events — is the sanctioned future direction, and would
  supersede this ADR.
