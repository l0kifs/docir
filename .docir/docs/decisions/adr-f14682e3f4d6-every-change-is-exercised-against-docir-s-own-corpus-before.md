---
code:
- CLAUDE.md
created: '2026-08-25'
description: The gates pass on defects that only a real store with history and a warm
  daemon exposes — 0.18.0 shipped three of them past a fully green suite.
id: adr-f14682e3f4d6
owner: maintainer
related:
- kind: refines
  to: adr-7d9fbbf976e8
- adr-354a4270ecd8
- rel-0c8d261640f6
status: accepted
tags:
- testing
- integrity
- agents
title: Every change is exercised against docir's own corpus before it is done
type: decision
updated: '2026-08-25'
---

## Context

adr-7d9fbbf976e8 requires that a feature's *instructions* be followed and the feature run, from
the state an adopter is in. That is a scratch store: `docir init`, two documents, a fresh index,
no daemon, no history. It is the right shape for "can somebody follow this", and it is the
wrong shape for almost everything else.

docir's own store is 170+ documents with real typed edges, real staleness, a schema baseline, an
index built by a previous version, and a long-lived daemon holding a warm model. Every one of
those is a condition a scratch store does not have and a unit test does not simulate.

## The evidence

The 0.18.0 release is the evidence. Every gate was green — ruff, ty, vulture, tach,
contract-sync, 2834 tests at 94% — and running the changed surfaces against this repository's
own corpus, through the daemon, found three things the gates could not:

- **`--also` and `--explain` reached the CLI and no MCP tool.** The vocabulary test pinned tool
  *names* against the dispatcher and said nothing about arguments, so an agent could not ask for
  either. That is the property adr-354a4270ecd8 exists to hold.
- **A benchmark figure in the docs had drifted** as the corpus grew — BM25 ordering moves with
  the documents behind it, and nothing recomputes prose.
- **`stale-index-build` fired on the version bump**, which is correct and which nobody had ever
  watched happen.

## Decision

Before a change is reported done, exercise **every surface it touched against this repository's
own store, through the default transport**. Not the scratch store, not only the suite: the
daemon, the real corpus, the commands a user types.

The two rules compose rather than overlap. adr-7d9fbbf976e8 asks *can somebody follow the
instructions*; this asks *does it work where the data is real*. Skipping either leaves a class
of defect that the gates provably do not catch.

## What "every surface" means

The commands and flags the change touched, plus the ones it could plausibly have broken — a
read path change is exercised through `context`, `search` and `query`; a schema change through
`check` and `reindex`; anything at all through the daemon at least once, because most work
happens with `--no-daemon` and the daemon is what users run.

Where a surface has a second transport, cross it. The MCP drift above existed because every
check of that release ran through the CLI.

## Why it is not automated

Same reason adr-7d9fbbf976e8 is not: a script that ran these commands would assert exit codes,
and every defect above was a *correct* exit code with the wrong content — a tool list missing an
argument, a number that no longer matched, a finding nobody had read. What catches those is
somebody looking at the output, which is the part a check cannot do.

What *is* mechanised is narrower and was added as each gap appeared: argument parity between
tool and command, ids in prose resolving, prose invocations resolving against the CLI tree.
