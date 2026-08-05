---
created: '2026-07-23'
description: Why the schema is a frozen domain-agnostic core plus swappable domain
  profiles.
id: adr-2a3f625bb2f8
owner: maintainer
related:
- kind: refines
  to: arch-1cfb1b212237
status: accepted
tags:
- schema
title: A frozen core schema + swappable domain profiles
type: decision
updated: '2026-08-05'
---

## Context
The bundled schema was three software-flavoured types (`decision`, `issue`,
`architecture`). Generalizing docir to other domains (research, ops, legal) meant
mutating that base set every time, with no separation between what is universal
and what is domain-specific.

## Decision
Split the bundled schema into a **frozen core** and named **profiles**:
- **core** (`infra/profiles.py::CORE_SCHEMA_YAML`) — domain-agnostic: the
  `decision` type (ADRs exist everywhere), the relation-kind registry, and
  staleness cadences. Always included.
- **profiles** — `software` (issue, architecture), `research` (hypothesis,
  experiment, finding), `ops` (runbook, incident, postmortem), `legal` (policy,
  contract, obligation). Each layers types on top of the core.

A `docs-schema.yaml` selects them with `profiles: [..]`; the loader merges
`core -> each named profile -> the file's own inline overrides` (later wins on
name conflicts). The default file is `profiles: [software]`, so the resolved
default type set is exactly the previous three — a zero-behaviour-change default.

Backward compatibility: a schema file with no `profiles:` key is parsed the old
inline-only way (no core injected, relations unconstrained), so hand-authored
schemas keep working untouched.

## Consequences
- Easier: generalizing to a new domain is picking a profile, not editing the
  base; the core stays small and stable.
- Harder: schema resolution now has a merge step (core + profiles + inline) with
  its own precedence and prefix-collision rules; documented in `profiles.py` and
  the default file's comments.
- Follow-up: profiles are bundled in-code as YAML strings; a future change could
  let users drop profile files into `~/.docir/profiles/` to add their own without
  editing the package.
