---
code:
- src/docir/modules/documents/domain/services/expressions.py
- src/docir/modules/documents/application/services/document_service.py
created: '2026-08-25'
description: query --expr filters on an expression over each document and its resolved
  edges, which is the ability to state a rule without docir shipping any.
id: adr-7316abc6be93
owner: maintainer
related:
- kind: refines
  to: adr-b2cfed9d5888
- issue-9b2d2ab09060
- ref-a3f4d3140e4e
status: accepted
tags:
- cli
- retrieval
- schema
title: A JMESPath expression over the corpus, and no rules of docir's own
type: decision
updated: '2026-08-25'
---

## Context

`query` shipped a fixed set of filters and every question outside it was a feature request.
issue-9b2d2ab09060 collected four the corpus can already answer and the CLI could not ask —
"which decisions are past their cadence and owned by nobody", "which documents have no inbound
edge except `relates_to`", "which issues point at a decision that has since been superseded".
Each is a projection or a join over data the index already holds.

## Decision

`docir query --expr '<JMESPath>'`, applied as a post-SQL predicate before the limit — the seam
`--stale` and `--code` already share, so `--expr ... --limit 10` means ten matching documents.

**JMESPath**, not JSONata and not a hand-rolled mini-language. One 20 KB dependency with no
dependencies of its own, a specified grammar, and no evaluation of arbitrary code: it reads
data and cannot call out, import or loop unboundedly. A language docir invented would have to
be documented, versioned and debugged by docir forever.

## Why this is not the rule engine adr-b2cfed9d5888 refused

That decision refused docir shipping **opinions about your architecture**, plus the machinery
those imply: a DSL of docir's own, a sandbox for user-supplied code, per-language static
analysis. A user writing a predicate over their own documents' metadata is not that. It is the
same act as `--owner platform-team --stale`, with a grammar instead of a flag.

The line to hold, and it is a bright one: **docir ships no rules, only the ability to state
one.** If a shipped default expression ever appears — a check docir runs unasked — this has
crossed back and the ADR is violated.

## The projection is the contract

An expression sees the document's own fields plus its edges **resolved in both directions**,
each edge carrying the other document's `type` and `status`. Resolution was open question 1 and
is answered by the motivating case: "an issue pointing at a superseded decision" is a question
about the *target's* status, and ids alone would ship a grammar without the case that justified
it. A target the corpus no longer carries keeps its id and reports `type`/`status` as null —
absent, not guessed; that edge is `dangling` and `check` is where it is reported.

The whole edge graph is read once per query and indexed both ways rather than looked up per
document, so the cost is independent of how many documents survive the SQL filters.

Because a user's expression is written against this shape, it is public surface and is spelled
out in the module's `CONTRACT.md`. Adding a key is additive; renaming one breaks expressions
written months ago against a corpus that still parses.

## Scope, and what is deliberately not here

**Named checks in `docs-schema.yaml`** — the other half of issue-9b2d2ab09060 — are not built.
They are where the rule-engine line actually gets tested, they need open question 2 answered
(a store's own rule cannot join `ERROR_KINDS` without letting one store's opinion fail another
build), and `--expr` is useful without them. Building the filter first also means the grammar
is exercised by hand before anything runs it unattended.

**Aggregates across documents** are out of reach by construction: "which types have more open
than closed" is a question about the corpus, and this is a per-document predicate. Three of the
issue's four questions are answerable; the fourth needs something this is not.

Open question 3 is answered yes: `docir_query` gains the argument, with the projection in its
description. An agent that can state a question does not need a flag minted for each one, and
an invalid expression is a `ValidationError` like an unknown tag.
