---
code:
- src/docir/modules/documents/application/services/document_service.py
- src/docir/entry_points/cli/read_cmds.py
- src/docir/entry_points/cli/write_cmds.py
- src/docir/entry_points/cli/emit.py
- src/docir/entry_points/doctor.py
- src/docir/entry_points/composition.py
- src/docir/entry_points/dispatch.py
- src/docir/modules/documents/application/dto.py
- src/docir/modules/documents/domain/services/checks
- src/docir/platform/persistence/repositories.py
created: '2026-09-11'
description: The eleven shapes that look like catalogue smells and are deliberately
  kept, and the shared read/write predicate that makes splitting DocumentService a
  regression.
id: adr-a1754eb79fe7
owner: maintainer
related:
- arch-322e5f992ad2
status: accepted
tags:
- architecture
title: The look-alikes the audit keeps, and why DocumentService stays whole
type: decision
updated: '2026-09-11'
---

## Context

A smell audit over `src/docir`, and a second pass over the split tree, named
nine findings and treated seven of them. This records the code both passes read
and deliberately left: eleven shapes that look like catalogue smells and are
kept, and one class that is a smell and is kept anyway.

It is a decision rather than an issue because none of it is work. An unstated
exemption reads as an oversight — a later reader cannot tell a judgement from a
miss, so they re-open it, or worse, "clean it up" — and an issue recording a
conclusion would stay open forever. The one finding that *is* work is
[[issue-55cc9295302a]].

## Exempt: the shipped agent contract

`docir query` (100 lines) and `docir update` (22 parameters) look like Long
Method and Long Parameter List. About 60 of `query`'s lines are its docstring,
and the parameters *are* `--help`, which is JSON when piped and so the one
surface an agent can parse without guessing. The same holds for the MCP
`docir_update`'s 20 arguments, from which the tool's input schema is derived.

Introducing a parameter object here would not tidy the surface. It would delete
it.

## Exempt: sequences that only look long

`doctor._store_findings` (105 lines) is eight uniform `if <flag>: append(...)`
guards with no interleaving and no block comments. Extracting each yields eight
one-branch functions — the needless-indirection direction, which is the smell
its own inverse cures.

`composition.build_container` (84 lines) is a composition root: linear wiring,
zero branching, the canonical exemption. `GraphChecker.check` is the rule
registry, one line per check, and its permissive-when-absent guards are the
documented convention rather than accidental complexity.

## Exempt: shapes the architecture mandates

`SqlAlchemyDocumentRepository` (18 methods) looks like Large Class. It is one
aggregate's repository, and the shared-index baseline deliberately keeps it in
`platform`; splitting it would widen a boundary edge that is only allowed to
shrink.

`Dispatcher._handlers` (22 entries) looks like Switch Statements. It is the
dispatch table that exists precisely so the two transports cannot answer
differently, and its keys are a public guard surface.

`DocumentView` (24 fields, no behaviour) looks like a Data Class. It is a
projection serialized over the daemon's JSON transport, which is the stated
exemption for that smell.

## Exempt: duplication that names something

The `emit` helpers in the CLI share a three-line `if use_json` skeleton and name
four different human renderings — a document, a batch, a list, a bare message.
Folding them into one function plus a render callback is the Middle Man
direction, and costs four names to save nine lines.

`UnitOfWorkFactory = Callable[[], UnitOfWork]` is declared in six modules. That
is the local convention, and changing it is a sweep of its own.

Constructor injection of eight or nine arguments is not a Long Parameter List:
those are collaborators, not values travelling together, so there is no object
for a parameter object to introduce.

The four rule classes under `checks/` share an identical two-line `__init__`.
Extract Superclass there would add an inheritance hierarchy holding one field to
save six lines, which is the Lazy Class inverse.

## DocumentService stays whole

`DocumentService` is 30 methods and 894 lines after the write-path staging and
the benchmark moved out. What remains still needs an "and": nine methods are the
write path and twelve are the read path, and those change for unrelated reasons.

It is left untreated on purpose, and this one is a recommendation rather than a
deferral. Splitting it moves `api.py`, its `CONTRACT.md` and the dispatcher,
which is a wider blast radius than the whole branch so far. More to the point,
both halves share `_is_visible`, whose own docstring records that ranked fusion
and graph expansion once tested different things and leaked a closed document
through the fourth path — "one predicate, both callers" is the fix, and a split
is how it comes back.

Treat it only alongside a reason to touch the public contract anyway.

## Exempt: assets.py holds styles and scripts together

`publishing/infra/assets.py` holds two kinds of thing and says so in its own
docstring: `STYLES` is ~380 lines that change for branding and layout, and
`FILTER_JS`/`SHELL_JS` are ~400 that change for behaviour — facet filtering, the
search palette, keyboard navigation, the sort keys. By the same test the rest of
this register applies, that is Divergent Change, and splitting it into
`styles.py` and `scripts.py` would be the treatment.

It is kept as one module because both are the same *kind* of thing to the code
that uses them: a string inlined into every page, for the reason the docstring
gives — a published site must work from `file://` with no CDN reachable, so
there is no asset pipeline and no second delivery mechanism to separate them
into. Neither half is logic; a reader never traces execution through either.

Recorded rather than left unstated because it was introduced deliberately, in
the commit that split `rendering.py`, and an unstated one reads as an oversight.
Revisit it if a third asset appears, or if either half stops being a single
constant.

## What would overturn one of these

Each exemption above is a reading of the code as it is, not a rule. The
catalogue is symmetric: every technique over-applied produces the smell its
inverse cures, so an exemption is the claim that this code sits at the right end
today — and requirements move.

Supersede this rather than editing an entry away. "We changed our mind about the
CLI docstrings" is a different fact from "we never looked at them", and only one
of them tells the next reader anything.
