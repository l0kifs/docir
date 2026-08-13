---
code:
- src/docir/modules/documents/application/dto.py
- src/docir/modules/documents/domain/services/graph_checks.py
created: '2026-08-13'
description: Structured queries are limited to the flags query ships with; every question
  outside that set is a feature request.
id: issue-9b2d2ab09060
owner: maintainer
related:
- ref-a6db21f52427
- adr-b2cfed9d5888
status: open
tags:
- retrieval
- cli
- schema
title: No expression language over the corpus
type: issue
updated: '2026-08-13'
---

## Context

docir has rich structure and exactly one way to interrogate it: the filters `query`
ships with (`--type --status --tag --owner --stale --code`, plus `--limit/--offset`).
Every question outside that set is a feature request, and the set only ever grows in
one direction.

Questions the corpus can already answer but the CLI cannot ask:

- "Which decisions are past their cadence *and* govern code no one owns?"
- "Which documents have no inbound edges except `relates_to`?" — i.e. nothing depends
  on them, which is different from `orphan`.
- "Which issues reference a decision that has since been superseded?"
- "Which types have more open than closed documents?"

Each is a projection or a join over data the index already holds. Answering them today
means either piping `query --limit 10000` into `jq` — which throws away the graph, since
skeletons carry edges but nothing resolves them — or adding a flag.

The adjacent market treats this as the product. DocHub's pitch is *architecture as data*:
JSONata over the model, and its validators are the same expressions with "must return
empty" attached (ref-a6db21f52427, gap 14). It is the one thing in that comparison docir
has no answer to, and the one docir is closest to being able to give — the structure is
there, the vocabulary is not.

## The tension this has to respect

adr-b2cfed9d5888 refused a rule engine, and that refusal must survive this. What it
refused was **docir shipping opinions about your architecture** plus the machinery those
imply: a rule DSL of docir's own, a sandbox for user-supplied code, per-language static
analysis. A user writing a predicate over their own documents' metadata is not that — it
is the same act as writing `--owner platform-team --stale`, with a grammar instead of a
flag.

The line to hold: docir ships **no rules**, only the ability to state one. If a shipped
default check ever appears in this feature, it has crossed back.

## Shape (not a decision — that is an ADR's job)

- **An expression over a document's own fields and its resolved edges.** JMESPath is the
  small, well-specified candidate: one dependency, a real grammar, no evaluation of
  arbitrary code. JSONata is more capable and much larger. A hand-rolled mini-language is
  the option to avoid.
- **`query --expr '<expression>'`**, applied as a post-SQL predicate before the limit —
  the seam `--stale` and `--code` already share (`_post_sql_predicate` / `_scanned_page`),
  so `--expr ... --limit 10` means ten matching documents.
- **Named checks a store declares**, in `docs-schema.yaml` beside the types they concern,
  evaluated by `check` as Tier 1 warnings. A store's own rule is exactly the kind of
  finding that must not gate CI on the schema's release cadence (the argument
  `schema-drift` and `missing-required` already make).
- The expression sees a **document projection**, not the ORM: id, type, status, tags,
  owner, verified, stale, code, and edges with their kinds in both directions. That is
  the contract to pin, because it is what a user's expression will be written against and
  what cannot then change silently.

## Open questions

1. Does the expression see *resolved* neighbours (the target's type and status) or only
   edge ids? Resolved answers "superseded successor" questions and costs a second pass.
2. Do named checks get a severity, or are they all warnings? `ERROR_KINDS` is currently a
   closed set derived from "the corpus is broken"; a user check cannot join it without
   letting a store's own rule fail someone else's build.
3. Does this reach MCP as a tool argument, and if so does an agent get to write
   expressions — or is it a human's authoring surface only?

## Why this is not urgent

Nothing is broken. Every question above has a manual answer, and the corpus sizes docir
targets make the manual answer cheap. This is the gap that decides whether docir stays a
retrieval tool or becomes one an organisation can query, and it should be built when
someone actually hits it — with their question as the first test.
