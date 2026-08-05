---
created: '2026-07-30'
description: The business outcome, scope and coverage the discovery run was framed
  against.
id: ref-9e4cce368b80
owner: maintainer
related:
- arch-1cfb1b212237
- adr-90e994d931cc
- issue-e183d47cdee1
status: active
tags:
- docs
title: Discovery frame — docir at v0.2.1, run 2026-07-26
type: reference
updated: '2026-08-05'
---

# Frame

Run: 2026-07-26 · analyst: Claude (agent) · repo: `docir` @ `main` `560aea5` (v0.2.1)

## Business outcome

- **Stated outcome** *(inferred from README:8-35, docs/doc-index-architecture.md)*:
  an AI coding agent working in a repository can (a) find the design knowledge relevant
  to the task it was given, cheaply, and (b) trust that what it finds is current and
  internally consistent — instead of re-deriving decisions or contradicting them.
- **Unit of value**: a *retrieval that changes what the agent does*. A decision found
  before the code is written is the whole product.
- **Success metric**: **NONE FOUND.** No telemetry, no analytics, no usage counters, no
  benchmark harness anywhere in the repo. → `issue-e183d47cdee1`.
  The README's own comparison table (README:39-48) is labelled *"Rough orientation, not
  a benchmark"*, i.e. the project's central claim (token-cheap, better retrieval) is
  explicitly unmeasured by its author.

## Who pays / uses / suffers

| Role | Relationship | Confidence |
|---|---|---|
| Repository maintainer adopting docir | Pays in setup + discipline; gets a durable decision log | inferred |
| AI coding agent (Claude Code et al.) | Primary *reader*; the token-cost optimisation targets it | observed (README:70-95, modules/agents) |
| Human developer | Secondary reader (Rich tables); primary *author* of intent | observed (rendering.py) |
| CI job | Runs `docir check --strict` as a merge gate | observed (app.py:419-440) |
| docir's own maintainer (Sergei Konovalov) | Sole decision owner for every rule below | observed (LICENSE, git log) |

**No revenue model, no tenancy, no accounts.** MIT, single-maintainer OSS. adr-90e994d931cc records
the deliberate absence of authorization. Consequence for this run: there is no "business"
with departments — the decision owner for *every* question is the maintainer. That is
recorded as a frame-level risk, not a per-question owner.

## Core vs supporting vs generic

- **Core domain** (the reason the product exists — depth goes here):
  the document lifecycle + Tier 0 schema enforcement, id allocation, the typed relation
  graph, staleness-as-data, and the hybrid retrieval ranking.
- **Supporting**: tag registry; agent-instruction scaffolding (`docir agent`); schema
  profiles; `docir init` bootstrap.
- **Generic**: persistence/SQLAlchemy, Unix-socket transport, daemon lifecycle, embedding
  backends, CLI rendering.

## Scope

**In scope** — the four bounded contexts and the store-resolution/entry layer:
`documents`, `tags`, `indexing`, `agents`, plus `config` (home resolution) and
`entry_points` (CLI/daemon as the trigger surface).

**Out of scope for this run** (recorded, not examined for business rules):
- Internal architecture conformance tooling (`tach.toml`, `scripts/check_contract_sync.py`)
  — engineering hygiene, not business behaviour.
- Packaging/release/CI workflow, logo assets, `docs/PUBLISHING.md`.
- The Alembic machinery itself (its *output* — the schema — is in scope).

## Decision owners

| Area | Owner | Notes |
|---|---|---|
| Everything | repo maintainer (`Sergei Konovalov`) | Single-maintainer project; no separable SME roles exist |

→ `issue-b928ad676595`: a single decision owner is also the single point of knowledge. Every
`unstated` rule in this register lives only in that person's head and in git history.

## Budget

- Extraction passes: P1–P5, single-agent (repo is 6 919 LOC / 105 files — fits one context
  with fidelity; the multi-agent cost check in SKILL.md §6 does **not** justify fan-out,
  and no delegation was requested).
- Bounded contexts analysed: 4 + config/entry.
- Question cap: ≤7 blocking questions per bounded context per round.
- Depth is **not** uniform: deepest on `documents` (core), shallowest on `agents` and
  transport (generic/supporting).

## Definition of done

Quality gates in `SKILL.md` §9, verified in `analysis/99-log.md` under `PHASE 7`.

## Frame-level unknowns (findings, not blockers)

1. No success metric exists → cannot rank any gap by measured impact. All `frequency`
   fields in `05-gaps.yaml` are therefore `unknown` unless a test or doc states otherwise.
   This is a real limitation on the prioritisation in this run.
2. No production observation, no support tickets, no user interviews available
   (non-interactive session, no telemetry in product). Evidence ranks 1, 5 and 6 from
   `extraction.md` §1 are **entirely absent**. Everything here rests on ranks 2–4 and 7.

## Note on paths (2026-07-30)

This document was `analysis/00-frame.md` until the discovery bundle was folded into docir's own store. The `analysis/...` paths in the text above describe where the run wrote its output at the time; those files are documents in this store now — see `docs/README.md` for the map.
