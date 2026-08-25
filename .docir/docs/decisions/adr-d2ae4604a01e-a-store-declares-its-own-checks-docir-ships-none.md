---
code:
- src/docir/modules/documents/domain/services/graph_checks.py
- src/docir/modules/documents/infra/schema_loader.py
created: '2026-08-25'
description: 'checks: in docs-schema.yaml runs a store''s own JMESPath rules as Tier
  1 warnings, which is how docir gains a validator without gaining an opinion.'
id: adr-d2ae4604a01e
owner: maintainer
related:
- kind: refines
  to: adr-7316abc6be93
- adr-b2cfed9d5888
- issue-9b2d2ab09060
status: accepted
tags:
- schema
- integrity
- cli
title: A store declares its own checks; docir ships none
type: decision
updated: '2026-08-25'
---

## Context

adr-7316abc6be93 shipped `query --expr` and deliberately left the other half of
issue-9b2d2ab09060 unbuilt: rules a store *declares*, run by `check` unasked. That is where the
line adr-b2cfed9d5888 drew actually gets tested — an expression docir runs on your behalf is
much closer to a rule than one you type — and the issue was explicit that it should wait for
somebody with a rule they actually wanted.

This corpus supplied one. Two `reference` documents were superseded by a newer compile and both
still carried `status: active`, so a reader filtering by status would be handed a document that
had been replaced. Neither `check` nor any flag could say so, and both types declare
`superseded` as a valid inactive status — the corpus simply had not been kept.

## Decision

`checks:` in `docs-schema.yaml`. A name, a JMESPath expression over the same projection
`query --expr` evaluates, and a message. `check` reports each match as a Tier 1 warning.

**docir ships none of them.** The grammar is docir's and every rule written in it is the
store's, which is what keeps adr-b2cfed9d5888 intact: that decision refused docir having
opinions about your architecture, not your ability to state yours. A shipped default expression
appearing here is how this crosses back, and it is the single thing to watch.

## Three rules that hold it up

**Always a warning.** `--strict` gates on `ERROR_KINDS`, which means "broken" in *docir's*
terms and must mean the same thing in every repository. A declared check joining it would make
`--strict` behave differently depending on whose schema is loaded. `--strict-all` already means
"everything is fatal" and covers a store that wants its own rules to gate.

**The name may not collide with a finding docir defines.** `RESERVED_FINDING_KINDS` is the whole
set, not just the error ones — reserving only the errors would let a store redefine `stale` or
`orphan`, and a reader could not tell whose finding they were reading.

**One projection, shared with `query --expr`.** A rule is written by trying it as a query and
declaring it once it finds what you meant. Two shapes would make it mean something subtly
different after declaration, which is the worst moment to discover a difference.

## Its first test

The rule above is declared in docir's own schema, found both violations on its first run, and
went silent once the two documents were retired. That sequence is the whole argument for having
waited: the feature's first exercise was a real question with real answers, not a fixture.

## What is still open

Whether a check can scope itself to a type, which every example so far has wanted to do with a
`type == '...'` clause and which reads fine. And whether the expression should see anything the
projection does not already carry — it does not see the body, deliberately, because a rule about
prose is a different feature with a different cost.
