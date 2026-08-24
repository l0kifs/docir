---
code:
- benchmarks/**
created: '2026-08-24'
description: benchmarks/ lives in the repository, so an adopter inherits docir's retrieval
  numbers as a claim with no way to reproduce them on their own documents.
id: issue-c6d184704682
owner: maintainer
related:
- ref-a6db21f52427
- adr-ab9c454b760c
status: resolved
tags:
- retrieval
- testing
title: The benchmark proves docir, not the adopter's corpus
type: issue
updated: '2026-08-24'
---

## What happens

`benchmarks/` is docir's strongest and least portable asset. It is the only published retrieval
measurement across every tool surveyed in ref-a6db21f52427, and it lives in the repository — so
a user who installs docir inherits the numbers as a claim and has no way to reproduce them, or
to find out whether their own corpus behaves the same way.

## Why it matters beyond marketing

This project has one rule about ranking changes: measure, then decide. adr-ab9c454b760c chose an
embedder on numbers and adr-d657a09b8c4a rejected a reranker on numbers. Every future ranking
question inherits that rule, and right now the instrument only exists for the maintainer, on one
corpus, in a git checkout.

That makes it a blocker rather than a nicety. A user who thinks retrieval is underperforming on
their documents cannot produce evidence, and the maintainer cannot ask for any.

## Shape of the fix

A fixture of queries with known-relevant documents, scored over the store the caller already
has. For docir the fixture is cheaper to express than for a path-addressed tool, because
expected results are document **ids** — stable under retitling, retyping and a moved file, which
is exactly what a fixture written six months ago needs to survive.

Reporting recall@k, MRR and precision@k against at least two configurations (with and without
graph expansion) is what makes a result readable, since ref-e7534f1c812d shows expansion lifts
both embedders and hides the difference between them.

## How it shipped

Shipped in `b1d4bb5` as `docir bench <fixture.yaml>`, with the three questions above answered
rather than deferred.

- **A command, not a recipe.** Writing the scoring yourself is the barrier this issue is about,
  so a documented recipe over existing output would have left it in place.
- **A plain file, not a store document.** `yaml.safe_load` parses the JSON spelling too, so one
  loader covers both, and judgments stay out of a corpus meant to hold decisions.
- **An unresolved id is neither an error nor a silent skip.** It is reported under `unresolved`
  and excluded from the judgments. Erroring makes one archived document fail the whole run;
  skipping quietly shrinks recall's denominator, which *raises* the score — a fixture rotting
  would read as retrieval improving. `StrategyScore.tasks` says how many tasks each mean
  covered, for the same reason. A task left with no resolvable ids is returned under `dropped`.

## What it reports, and why three rows

`context` is the shipped read path. `context --expand 0` removes graph expansion, which lifts
every embedder and hides the difference between them (ref-e7534f1c812d) — the pair is what
isolates the semantic signal. `search` is full-text alone, the floor anything semantic must beat.

`benchmarks/example_fixture.yaml` judges eight tasks against docir's own store and scores
`context` 0.88 recall@5 / 0.63 MRR, `--expand 0` 0.75, `search` 0.62. That ordering is the
design working on a real corpus rather than a fixture built to show it.

Two properties follow from what a fixture is. It names document **ids**, not paths, because a
retitle moves the filename and a retype moves the directory. And it does not federate: a
fixture judges ids in one store, and the score is a property of that store's read path.
