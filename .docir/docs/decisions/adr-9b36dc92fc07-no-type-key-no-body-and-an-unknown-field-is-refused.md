---
code:
- src/docir/modules/documents/domain/services/expressions.py
created: '2026-08-25'
description: The two questions store checks left open answer to 'nothing to add',
  and answering them found that a mistyped field matched nothing silently.
id: adr-9b36dc92fc07
owner: maintainer
related:
- kind: refines
  to: adr-d2ae4604a01e
- adr-7316abc6be93
- adr-f0fb4833ab04
status: accepted
tags:
- schema
- cli
- integrity
title: No type key, no body, and an unknown field is refused
type: decision
updated: '2026-08-25'
---

## Context

adr-d2ae4604a01e left two questions: whether a declared check should be able to scope itself to
a type, and whether an expression should see the document's body. Answering them turned up a
third fault that mattered more than either.

## Type scoping: no key, the expression already does it

`type == 'decision' && …` works today, composes (`type != 'issue'`, an `in` over several) and
needs nothing added. A `type:` key beside `expr:` would be a second way to say one thing, and
the first thing a reader would have to ask is which wins when both are present.

Efficiency is not an argument at these corpus sizes: the projection is a dict of fifteen keys
and the scan is already one pass.

## The body: no, and every rule that wants it has a better-typed alternative

The projection carries `title` and `description` because they are *fields with a contract* — a
description is a one-sentence summary by definition. A body is unstructured, and a rule over it
is a guess about prose.

That is the same fault adr-f0fb4833ab04 rejected a check for on the same day: prose naming a
path is not evidence of governance, because a mention and a meaning are indistinguishable in
text. `contains(body, 'TODO')` fires on the document *about* TODOs.

Every concrete rule that wanted the body had a better-typed form — a tag, which is registered
and validated; a status; a field. A store reaching for the body is usually reaching for a
convention it has not declared yet.

## What answering them found: an unknown name was silent

JMESPath evaluates an unknown identifier to `null` rather than raising. So `stauts == 'open'`
matched nothing, returned an empty result, and read exactly like a corpus with nothing wrong —
and a *declared* check carrying that typo would have run on every `check` forever, finding
nothing, and looking like a rule that passes.

`compile_expression` now walks the parsed AST and refuses any identifier the projection does
not carry, naming what would have worked. `PROJECTION_FIELDS` and `EDGE_FIELDS` are declared
constants pinned by a test asserting `project()` returns exactly them, so a field added to one
without the other fails rather than becoming quietly unwritable.

## It caught docir's own documentation immediately

Bare `null` in JMESPath is an **identifier**, not a literal — the literal is `` `null` ``. So
`owner == null` compares a key no document carries against itself, which is `None == None`,
which is the answer the author wanted. It worked, for the wrong reason, and it was the example
in the skill, the CLI docstring, the MCP tool description and the changelog — every place this
feature was documented. All four are now `` owner == `null` ``.

That is the strongest argument for the guard: the first thing it refused was written by the
person who built the feature, in the documentation teaching it.
