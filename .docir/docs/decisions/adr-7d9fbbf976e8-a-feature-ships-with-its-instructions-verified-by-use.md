---
code:
- README.md
- src/docir/entry_points/cli/app.py
- src/docir/modules/agents/infra/templates/**
created: '2026-08-24'
description: A business feature is done when an agent holding only the installed package
  can tell what it is, when to reach for it and how to invoke it — and somebody has
  followed those instructions to check.
id: adr-7d9fbbf976e8
owner: maintainer
related:
- adr-bea42e359960
- adr-3a2d5ee7bc84
status: accepted
tags:
- agents
- docs
- testing
title: A feature ships with its instructions, verified by use
type: decision
updated: '2026-08-25'
---

## Context

The CI gates prove a feature works. Nothing proves anybody can find it, and docir's user is an
AI agent that will never read this repository — it has the installed wheel, the skill `docir
agent install` wrote, and `--help`. Everything else in the repo is invisible to it.

That gap is not hypothetical. `docir bench` shipped with its only worked fixture at
`benchmarks/example_fixture.yaml`, a path the wheel does not contain — 213 entries, zero
benchmark files — while the skill named the fixture's *shape* without showing it or saying
where the document ids come from. Both surfaces read as complete to their author. An agent
following them would have written a fixture of invented ids, and `bench` would have reported
every task dropped and measured nothing.

## Decision

A business feature is done when an agent holding **only the installed package** can tell what
it is, when to reach for it, and how to invoke it — including how to obtain any input it needs.

Three surfaces carry that, and all three ship with the change:

- the **packaged skill** (`modules/agents/infra/templates/skill.md`) — what and *when*;
- the **CLI docstring** — *how*, with a worked example, since `--help` is JSON when piped and
  is the one surface an agent parses rather than guesses at;
- **`README.md`** — for the human deciding whether to adopt docir.

Edit the template, never `.claude/skills/**`, then run `docir agent update` so this repo's own
copies match what an adopter installs.

## Verification is use, not review

The instructions are then **followed**, from the state an adopter is in, and the feature run.
Re-reading what you wrote and judging it sufficient is exactly what produced the gap above. If
a step needs data, the instructions have to say where that data comes from, and following them
has to produce it.

This is adr-bea42e359960's rule one level out. That decision validates docir's prose against
the *command tree*, so a documented invocation cannot name a flag that does not exist. It
cannot tell whether the prose is enough to act on, because a resolvable command proves shape
and not sufficiency.

## Consequences

A feature costs more than its implementation, deliberately. The cost is bounded — three
surfaces and one run — and it falls on the change that introduced the feature, where the author
still knows what they meant.

It is **not** automated and should not be: a check that the skill mentions every command would
pass on a sentence naming it, which is the failure this decision exists to catch. What is
mechanised already is the narrower claim adr-bea42e359960 owns.
