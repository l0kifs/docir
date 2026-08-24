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
status: open
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

## What is not decided

- Whether it ships as a command or as a documented recipe over existing output.
- Whether the fixture format is a new file type in the store or a plain JSON path argument.
  A store document would be validated and retrievable, and would also put test data in a corpus
  that is meant to hold decisions.
- Whether a fixture naming a document that no longer exists is an error or a skipped row.
