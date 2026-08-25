---
code:
- src/docir/modules/documents/domain/schema.py
created: '2026-08-25'
description: Giving implements a machine meaning would warn on ordinary modelling,
  so it stays a word for the reader — and a kind gains a property on evidence, not
  on symmetry.
id: adr-bbfac38a82b6
owner: maintainer
related:
- kind: refines
  to: adr-716c2eeb4e51
- adr-234b956a48d8
status: accepted
tags:
- schema
- integrity
title: implements carries no property, and that is the decision
type: decision
updated: '2026-08-25'
---

## Context

Sweeping which code reads which relation-kind property produced a map, and `implements` was the
one row with nothing in it. Every other core kind changes something docir does; `implements`
changes nothing that `relates_to` would not.

## The map

| kind | symmetric | dependency | blocking | successor | what reads it |
|---|---|---|---|---|---|
| `relates_to` | ✓ | | | | cycle exemption |
| `contradicts` | ✓ | | | ✓ | cycle exemption, `context` expansion |
| `supersedes` | | | | ✓ | `context` expansion |
| `depends_on` | | ✓ | ✓ | | `layering`, `unblocked` |
| `refines` | | ✓ | | | `layering` |
| `implements` | | | | | nothing |

Each property has exactly one consumer, and that is what makes the table worth keeping: it is
the thing nobody could see when `unblocked` was pointed at `dependency`, and it is where the
next such mistake would show up first.

## Decision

`implements` stays inert. It carries no property, and that is a choice rather than an oversight.

The obvious change was `dependency: true`, on the reading that an implementation relies on what
it implements. Measured against the layering check, it produces a false positive on ordinary
modelling:

    decision(3)     implements architecture(5)  ->  silent
    architecture(5) implements decision(3)      ->  WARNING

## Why the direction is the problem

"This architecture implements ADR-7" is a completely normal thing to write, and it would warn.
`refines` survives the same test because its direction is reliable — the narrower refines the
broader, so the source is always the more concrete of the two. `implements` has no such
direction: the implementer may be more concrete than what it implements or less, depending on
whether you are pointing from the plan to the rule or from the rule to the plan.

A warning that fires on correct usage is the failure the layering check was already fixed for
once, and it is how a corpus learns to ignore the whole of `docir check` — which is where the
duplicate-id detection lives.

`blocking: true` is wrong for the same reason it is wrong for `refines`: a document
implementing something *closed* is not ready to start, it is implementing something retired.

## The rule this sets

**A kind gains a property on evidence, not on symmetry.** The fact that five of six kinds carry
one is not an argument that the sixth should. What would reopen this is somebody's corpus where
an `implements` edge should have produced a finding and did not — a real edge, in a real repo,
with the finding it was denied.

Until then `implements` earns its place the way a well-chosen word does: a reader of the
frontmatter learns something `relates_to` would not have told them, and docir does nothing
with it. That is a legitimate thing for a vocabulary to contain.
