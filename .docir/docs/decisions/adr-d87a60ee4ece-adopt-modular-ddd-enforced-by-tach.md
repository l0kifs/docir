---
code:
- tach.toml
- scripts/check_contract_sync.py
created: '2026-07-22'
description: Why the codebase is vertical bounded-context modules with tach proving
  the boundaries in CI.
id: adr-d87a60ee4ece
owner: maintainer
related:
- kind: implements
  to: arch-322e5f992ad2
status: accepted
tags:
- architecture
- testing
title: Adopt Modular DDD enforced by tach
type: decision
updated: '2026-08-06'
---

## Context
The codebase was organized as Clean Architecture with technical layers at the
project root (`domain/`, `application/`, `infrastructure/`, `presentation/`).
`docs/ARCHITECTURE_RULES.md` calls instead for vertical bounded-context modules
with machine-checked boundaries, so that adding a feature touches one module
plus wiring and the tooling can prove it. Conventions without enforcement decay.

## Decision
Restructure into `config/`, `platform/` (shared technical capability),
`modules/<context>/` (each with `api.py`, `CONTRACT.md`, and `domain` /
`application` / `infra` layers), and `entry_points/` (thin wiring). The bounded
contexts are `documents`, `tags`, and `indexing`. Enforce boundaries with
[tach](https://docs.gauge.sh): each module layer plus its `api` is a distinct
tach module, dependencies are declared explicitly, cycles are forbidden, and
`tach check` runs in CI alongside a contract-sync gate. Introduce the linter
first over the old layout (permissive baseline), then restructure — per §12.

## Consequences
- Easier: locating a capability; reasoning about a module from its `CONTRACT.md`
  without reading source; proving no illegal import was added.
- Harder: cross-cutting changes must respect the public `api` surface; adding a
  dependency requires declaring it in `tach.toml`.
- Now forbidden: importing another module's internals (only its `api`); import
  cycles; technical-layer directories at the project root.
