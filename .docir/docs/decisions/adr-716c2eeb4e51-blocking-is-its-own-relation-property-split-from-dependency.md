---
code:
- src/docir/modules/documents/domain/schema.py
- src/docir/modules/documents/domain/services/graph_checks.py
created: '2026-08-25'
description: One flag was answering two questions — where two types sit, and whether
  one waits for the other — so a decision refining a superseded one read as ready
  to start.
id: adr-716c2eeb4e51
owner: maintainer
related:
- kind: refines
  to: adr-234b956a48d8
- issue-9b2d2ab09060
status: accepted
tags:
- schema
- integrity
title: Blocking is its own relation property, split from dependency
type: decision
updated: '2026-08-25'
---

## Context

The `unblocked` check reads a relation-kind property to decide which edges are blockers. It
shipped reading `dependency`, justified at the time as "exactly the property *the source relies
on the target*". That reasoning was too loose, and a sweep of which code reads which property
found why: **`dependency` is consumed by two checks asking different questions.**

- **Layering** asks a *structural* question: does the source sit above the target in the type
  hierarchy? A higher-level type depending on a lower-level one is the violation.
- **`unblocked`** asks a *temporal* one: does the source wait for the target to finish?

`depends_on` answers both. `refines` answers only the first — it says the source *narrows* the
target, which is a claim about scope and none about time.

## What it looked like

Reproduced against a real store: a decision that `refines` another, after the target was
superseded, reported

    'adr-...' is ready to start: everything it depends on has closed

which is backwards. A narrowing whose broader rule was just retired is a problem, not a green
light. `refines` is the most-used kind in docir's own corpus — 34 edges across 31 documents —
so the misreport was latent everywhere, silent only because no target had closed yet.

## Decision

A fourth relation-kind property, **`blocking`**: the source waits for the target. `unblocked`
reads it; nothing else does. Of the core kinds only `depends_on` carries it, and it carries
`dependency` too.

The alternative was to hardcode `depends_on` in the check, which adr-234b956a48d8 forbids for
the reason it gave: a custom kind with exactly that shape could never join, and nothing would
say so. A store that models `blocked_by` declares `blocking: true` and gets the finding.

## Why a property with one core member is not too thin

`successor` had two, `dependency` has two, and this has one — but member count is not what
justifies a property. What justifies it is that two consumers were reading one flag for two
claims, and no amount of care at the call site fixes that: the *name* `dependency` reads as
"relies on", which is true of `refines` in the structural sense and false in the temporal one.
Splitting is what makes the two questions separately answerable, and separately wrong.

## Consequences

Every store sees this as `schema-drift` on upgrade — a relation kind gained a property, which
is exactly what that finding exists to report. Nothing else changes for a corpus that does not
declare the new property: `blocking` defaults to false, so a custom kind adds no finding until
its author asks, which is the asymmetry the other three already follow.

`unblocked` now fires on strictly fewer edges than it did. That is the fix, not a regression:
the edges it stops firing on were the ones it was wrong about.
