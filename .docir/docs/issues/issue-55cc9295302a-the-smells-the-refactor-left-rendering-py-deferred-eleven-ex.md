---
code:
- src/docir/modules/publishing/infra/rendering.py
- src/docir/entry_points/cli/app.py
- src/docir/entry_points/doctor.py
- src/docir/entry_points/composition.py
- src/docir/entry_points/dispatch.py
- src/docir/modules/documents/application/dto.py
- src/docir/platform/persistence/repositories.py
created: '2026-09-11'
description: Why publishing/infra/rendering.py is the one audited smell still untreated,
  and the evidence exempting the eleven look-alikes the audit read and left.
id: issue-55cc9295302a
owner: maintainer
related:
- arch-322e5f992ad2
- adr-a343140d72e2
status: open
tags:
- architecture
- cosmetic
title: 'The smells the refactor left: rendering.py deferred, eleven exempt'
type: issue
updated: '2026-09-11'
---

## Context

A smell audit over `src/docir` named six findings and treated all six on branch
`refactor/split-large-classes`. The commits carry the named smell, the technique,
the measure and the evidence for each, so none of that is repeated here.

What a commit cannot carry is the code the audit read and deliberately did not
touch. An unstated exemption reads as an oversight — a later reader cannot tell
a judgement from a miss, so they re-open it, or worse, "clean it up". This is
that register: one finding deferred, eleven exempt.

## The deferred finding: rendering.py

`src/docir/modules/publishing/infra/rendering.py` is 2,072 lines over five
concerns — CSS constants, the index page, the document page, the chips, and the
markdown pipeline. Divergent Change is real: the file changes for branding
reasons, for site-structure reasons and for linkify reasons, independently.

It was left because splitting it is a multi-file sweep, not one
behaviour-preserving move, and that is a different kind of change from the six
that shipped. Two things any attempt must respect: the module docstring records
layout decisions measured in a browser rather than reasoned from the markup, and
it has to travel with the code it explains; and the module is a leaf that takes
documents as data, which is what keeps it out of the aggregate.

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

The four `_emit_*` helpers in the CLI share a three-line `if use_json` skeleton
and name four different human renderings. Folding them into one function plus a
render callback is the Middle Man direction, and costs four names to save nine
lines.

`UnitOfWorkFactory = Callable[[], UnitOfWork]` is declared in six modules. That
is the local convention, and changing it is a sweep of its own rather than part
of this pass.

Constructor injection of eight or nine arguments is not a Long Parameter List:
those are collaborators, not values travelling together, so there is no object
for a parameter object to introduce.

## What would close this

An edge case that is not one: `lint --deep` reaches no MCP tool and looks like
transport drift. It is a confirmation guard whose documented behaviour is that
without it the command does nothing, so a tool argument would have exactly one
legal value. The write-path parity guard now states that exemption where a test
enforces it.

This issue resolves when `rendering.py` stops changing for three unrelated
reasons — or when a reading of it concludes the five concerns are one after all,
which is an answer worth recording rather than a failure to act.
