---
created: '2026-07-30'
description: 'Scope, method and budget for the second discovery pass: the surface
  v0.2.1 never examined, probed rather than read.'
id: ref-0f48dc93d435
owner: maintainer
related:
- kind: supersedes
  to: ref-9e4cce368b80
- ref-32cb4f874fbe
status: active
tags:
- docs
title: Discovery frame — docir at 0.8.0+, run 2026-07-30
type: reference
updated: '2026-07-30'
---

# Discovery frame — docir at 0.8.0+, run 2026-07-30

Run: 2026-07-30 · analyst: Claude (agent) · repo: `docir` @ `main` `869e618`
Predecessor: the v0.2.1 frame, `ref-9e4cce368b80`. Read that one first — the business
outcome, the unit of value and the actor set are unchanged, and this frame records only
what is different about *this* run.

## Why re-run

The previous pass ran against v0.2.1. Eight releases later, 35 of its 50 gaps have code or
tests naming them, and its rule register carries **38 rules still marked `assumed`** —
reconstructed from code, never confirmed by anyone who could say what was intended. More
importantly, the last pass named what it did **not** examine, and that list has since grown
features: the daemon transport and lifecycle, the embedding scheduler, `lint --deep`, the
agents module and Alembic were all unexamined then, and `init`/per-project stores, schema
profiles, typed edges, staleness, pagination, the `reference` type, tag usage counts and
the tag-key grammar did not exist.

## Scope for this round

**In:** the surface the previous pass did not read, plus everything added since v0.2.1.
Priority order — daemon transport and lifecycle · embedding scheduler · `lint --deep` ·
agents module · Alembic migrations · `init` and store discovery · schema profiles · typed
relation edges · staleness · pagination.

**Out:** re-deriving the 38 `assumed` rules. They are a separate exercise needing a human
who can say what was intended, not another agent reading the same code (that is what
archived issue GAP-002 recorded). Also out: the ranking algorithm's constants, which
`benchmarks/` measures rather than reasons about.

## Method

**Probe first, read second.** Every defect worth having from the previous pass, and all
four found earlier today, came from running the CLI as a user would — not from reading the
suite. A test that has never failed has not been shown to work, and a rule read off code is
a claim about the code, not about behaviour. So each area gets executed against a
throwaway store before anything is written down, and every finding cites the probe that
produced it.

## Budget and definition of done

One round. Findings are written as `issue` documents (`docir add --type issue`), numbered
GAP-052 onward to continue the register; questions Q-018 onward. Done when every area in
the priority list has either a finding, a confirmed rule, or an explicit line in the
coverage log saying it was not reached.

## Decision owner

The repo maintainer, for everything — unchanged, and still the finding recorded as GAP-002.

## Artifacts

No `analysis/` directory: it was deleted on 2026-07-30 when the discovery bundle was folded
into docir's own store, and re-creating it would undo that. Findings, questions, the probe
log and this frame are documents here. `docs/README.md` maps the old paths.
