---
code:
- src/docir/modules/documents/application/dto.py
- src/docir/modules/documents/domain/services/graph_checks.py
created: '2026-08-13'
description: The filter half shipped as query --expr; named checks a store declares
  in its schema are what remains, and are where the rule-engine line gets tested.
id: issue-9b2d2ab09060
owner: maintainer
related:
- adr-b2cfed9d5888
- ref-a6db21f52427
- adr-7316abc6be93
status: open
tags:
- retrieval
- cli
- schema
title: No expression language over the corpus
type: issue
updated: '2026-08-25'
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

## Why the adjacent market treats this as the product

DocHub's pitch is *architecture as data*:
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

## What shipped

The filter half shipped as `docir query --expr '<JMESPath>'` — adr-7316abc6be93 records the
choices. Three of the four questions above are now askable:

```bash
docir query --expr "stale && owner == null"
docir query --type issue --expr "related[?status=='superseded']"
```

The fourth — "which types have more open than closed documents" — is out of reach by
construction. It is a question about the corpus and this is a per-document predicate.

## The three open questions, answered

1. **Resolved neighbours, not ids.** Decided by the motivating case: "an issue pointing at a
   superseded decision" is a question about the *target's* status, so ids alone would have
   shipped a grammar without the case that justified it. The whole edge graph is read once per
   query and indexed both ways, so the cost does not grow with how many documents survive the
   SQL filters.
2. **Not answered, because named checks are not built.** Severity only matters once a store's
   own rule can produce a finding, and that half is deliberately deferred.
3. **Yes, MCP.** `docir_query` takes `expr`, with the projection spelled out in its
   description. An agent that can state a question does not need a flag minted for each one,
   and an invalid expression is a `ValidationError` like an unknown tag.

## What is left

**Named checks a store declares in `docs-schema.yaml`**, evaluated by `check` as Tier 1
warnings. That is where the line adr-b2cfed9d5888 drew actually gets tested — an expression
docir *runs unasked* is much closer to a rule than one a person types — and it needs question 2
settled first: a store's own rule cannot join `ERROR_KINDS` without letting one store's opinion
fail another repository's build.

Building the filter first was deliberate. The grammar and the projection get exercised by hand,
against a real corpus, before anything runs them unattended.

## Why the rest is still not urgent

The filter half is built, so the questions above have an answer that is not `jq`. What
remains — checks a store runs unasked — is the half that decides whether docir stays a
retrieval tool or becomes one an organisation governs with, and it carries the risk the
filter does not. Build it when someone actually hits it, with their rule as the first test.
