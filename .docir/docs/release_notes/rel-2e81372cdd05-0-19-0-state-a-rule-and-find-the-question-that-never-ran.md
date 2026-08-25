---
created: '2026-08-25'
description: 'checks: lets a store declare its own rules in docir''s grammar, and
  the guard added alongside found that a mistyped expression had been silently matching
  nothing.'
id: rel-2e81372cdd05
owner: maintainer
related:
- adr-d2ae4604a01e
- adr-9b36dc92fc07
- adr-f0fb4833ab04
- adr-7316abc6be93
- adr-b2cfed9d5888
- adr-f14682e3f4d6
- rel-0c8d261640f6
status: published
tags:
- release
- schema
- integrity
title: 0.19.0 — state a rule, and find the question that never ran
type: release_note
updated: '2026-08-25'
---

## What this release is about

0.18.0 gave a grammar for asking questions of the corpus. 0.19.0 lets a store **state a rule**
in that grammar — `checks:` in `docs-schema.yaml`, evaluated by `check` as Tier 1 warnings —
and, while answering the questions that feature left open, found that a mistyped question had
been answering "nothing wrong" all along.

Released 2026-08-25. `CHANGELOG.md` and the GitHub release carry the full text; this carries
the edges.

## What an upgrader must do

`owner == null` now errors. Bare `null` is a JMESPath identifier, not a literal, so the old
form compared a key no document carries against itself — the answer you wanted, for the wrong
reason. Rewrite as `` owner == `null` ``. Every `--expr` example docir shipped in 0.18.0 used
the wrong form, so anything copied from those docs needs the same edit.

Nothing else changes without asking: a store declaring no `checks:` behaves exactly as before.

## The line this release walks

adr-b2cfed9d5888 refused a rule engine. adr-d2ae4604a01e adds one and does not contradict it,
because what that decision refused was docir having opinions about your architecture — not your
ability to state yours. **docir ships no expressions.** The single thing to watch in any future
change here is a shipped default appearing, which is how it crosses back.

## What it cost to be sure

The feature waited for a rule somebody actually wanted, and the wait is why it works: the first
rule declared found two real violations in docir's own corpus and went silent when they were
fixed.

Two checks were measured and *not* built this cycle — a `code:`-coverage advisory
(adr-f0fb4833ab04) and, in the same week, a query rewriter and a generative dependency. The
pattern is the point: the instrument shipped in 0.18.0 is what makes "no" an answer with a
number behind it.
