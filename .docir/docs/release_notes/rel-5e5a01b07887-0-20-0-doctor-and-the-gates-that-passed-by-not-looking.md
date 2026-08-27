---
created: '2026-08-27'
description: '`docir doctor` reports the conditions that make docir answer wrongly
  without failing — added while fixing four of this project''s own gates that were
  green because they read nothing.'
id: rel-5e5a01b07887
owner: maintainer
related:
- adr-909734bced92
- adr-fe7c91f61f32
- adr-e18250eb3081
- adr-1cccd77cb023
- adr-f14682e3f4d6
- issue-87410666c867
- issue-82b01d7f80d0
- issue-b323a5b2ba18
- issue-28e5dc0191cd
- issue-9509f9fa3631
- rel-2e81372cdd05
status: published
tags:
- cli
- integrity
- release
- retrieval
title: 0.20.0 — doctor, and the gates that passed by not looking
type: release_note
updated: '2026-08-27'
---

## What this release is about

0.19.0 let a store state a rule, and found that a mistyped question had been answering
"nothing wrong" all along. 0.20.0 is that discovery generalised: four gates in docir's own
project were green **because they were not looking** — a merge gate reading an index no CI
checkout has, a diagram check asserting a file existed rather than a diagram drawing, a model
cache naming a directory fastembed had stopped writing to, and a workflow error that stopped
every job while the YAML parsed fine.

`docir doctor` (adr-909734bced92) is the command for that class: conditions that raise nothing
and produce an answer imitating a correct one. Each was already detected somewhere — none was
reportable together.

Released 2026-08-27. `CHANGELOG.md` and the GitHub release carry the full text; this carries
the edges.

## What an upgrader must do

`docir check` now reports `empty-index`, and it is an **error**. A `check --strict` on a fresh
clone with no rebuild in front of it starts failing — correctly: measured on this corpus, one
linked-to document removed produced zero findings before a reindex and sixteen `dangling`
errors after. Run `docir reindex` first.

The packaged skill is a directory now, and installing **regenerates** it — every `.md` under it
this build does not ship is deleted. Hand-edited files under `.claude/skills/docir/` will not
survive `docir agent update`. Run it after upgrading; nothing detects a stale skill later.

Nothing else changes without you asking.

## The line this release walks

adr-1cccd77cb023 promotes a finding to `error` in a codebase whose standing rule is not to, and
the distinction is the whole argument. Every warning docir refuses to promote —
`schema-drift`, `stale-index-build`, `code-changed` — describes something that moved and *still
answers*, so an error there red-builds a correct setup.

`empty-index` describes an index that answers nothing, and red-builds a setup that was never
checking anything. The test it had to pass: a warning would have changed nothing, because an
adopter's `check --strict` would still have been green over an empty graph.

## What it cost to be sure

None of these was found by reading the suite. issue-87410666c867 surfaced while placing a
`doctor` step in CI; issue-82b01d7f80d0 by reading a run's step timings, where a reindex took
100s against 70s locally; issue-b323a5b2ba18 by pushing a workflow that GitHub then refused;
issue-28e5dc0191cd by rendering a page in a browser rather than reading a bundle.

That is adr-f14682e3f4d6's rule paying out twice in one cycle — the gates prove a feature
works and cannot prove anyone can reach it. The instrument each defect left behind is the
durable half: `actionlint` before a push, a browser assertion instead of a file check, and
`doctor` itself.
