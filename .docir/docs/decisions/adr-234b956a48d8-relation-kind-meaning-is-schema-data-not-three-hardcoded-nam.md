---
code:
- src/docir/modules/documents/domain/schema.py
created: '2026-08-05'
description: Custom relation kinds could join none of the sets that decide cycles,
  layering and successor traversal, so they were silently exempt from all three; symmetric/dependency/successor
  become declarable properties.
id: adr-234b956a48d8
owner: maintainer
related:
- kind: refines
  to: adr-599055502f0e
- issue-44875a5a6ca6
- issue-40d1792bc9f9
- arch-1cfb1b212237
status: accepted
tags:
- schema
- architecture
- integrity
title: Relation-kind meaning is schema data, not three hardcoded name sets
type: decision
updated: '2026-08-06'
---

## Context

A relation kind is a string. What one *means* was decided by three hardcoded
frozensets, in three different modules:

- `graph_checks._DEPENDENCY_KINDS` = {`depends_on`, `refines`} — the only kinds a
  `layering` warning could be read from.
- `graph_checks._DIRECTED_KINDS` = {`supersedes`, `depends_on`, `refines`,
  `implements`} — the only kinds a `cycle` could be read from (added by
  issue-44875a5a6ca6, one commit before this).
- `document_service._SUCCESSOR_KINDS` = {`supersedes`, `contradicts`} — the kinds
  `context` expansion follows *backwards*, so a hit carries its own replacement.

The schema has always let a store register extra kinds (`relation_types:
[governs, blocks]`), and a kind so registered is a first-class Tier 0 citizen:
the validator accepts it, `allowed_relations` constrains it, it round-trips on
disk. But it could join none of those three sets. A custom kind was therefore
exempt from layering, exempt from successor traversal, and — after
issue-44875a5a6ca6 — exempt from cycle detection too. Nothing anywhere said so.

That last one was a regression this project introduced deliberately and then had
to reckon with. Before it, every kind was cycle-checked; `A blocks B blocks A`
was caught. Narrowing to an allowlist fixed 127 false cycles on symmetric edges
and silently dropped a true positive class on the way.

The pattern is by now familiar. Both dependency and direction began as
*exemption* lists, and both were wrong the same way: everything not exempted
carried the claim, including `relates_to`, which is what a bare id in `related:`
means. Layering fired permanently on a decision linking its motivating issue
(issue-40d1792bc9f9); cycles fired permanently on any pair of documents that
mentioned each other. Each was fixed by inverting to an allowlist, and each
inversion moved the problem onto custom kinds rather than removing it.

## Decision

Relation-kind meaning becomes schema data. `relation_types:` accepts a **mapping**
of kind name to properties alongside the list form it has always accepted:

```yaml
relation_types:
  governs:     {dependency: true}
  duplicates:  {symmetric: true}
  replaced_by: {successor: true}
  blocks:      {}
```

Three properties, each read by exactly one consumer:

- **`symmetric`** — `A -kind-> B` and `B -kind-> A` are the same statement. The
  cycle check skips these edges.
- **`dependency`** — the source relies on the target. The layering check reads
  only these.
- **`successor`** — the incoming direction answers "is this still current?".
  `context` expansion follows these backwards.

All three default to **false**, which is asymmetric on purpose. `symmetric: false`
means the kind *is* cycle-checked, so a custom kind keeps the coverage it had
before kinds were distinguished at all. `dependency: false` and `successor: false`
mean it adds no warning and changes no traversal until asked. The rule is "check
what you already checked; do nothing new".

The six core kinds carry their properties in **`schema.CORE_RELATION_KINDS`**, not
in `CORE_SCHEMA_YAML`. A schema with no `profiles:` key never merges the core
file, and those exist — inline-only parsing is the documented backward-compatible
path. Declaring the properties only in YAML would leave every such store with a
non-symmetric `relates_to`, which is issue-44875a5a6ca6 reintroduced through the
back door. A declared property overrides the core default; a partial declaration
leaves the rest of that kind alone.

## Consequences

- A custom directed kind is cycle-checked again, and a custom symmetric one can
  say so instead of being wrong in one direction or the other.
- `replaced_by`, `revokes` and anything else shaped like `supersedes` can now be
  followed backwards by `context`. This was previously impossible at any price.
- `docir schema show` reports the *resolved* properties of every kind, because a
  core kind carries meaning without appearing in the file — the merged view is
  the only place the question can be answered.
- The three frozensets are gone. Their history stays as a comment in
  `graph_checks`: both were exemption lists first, and both fired on correct
  usage until inverted.
- Layering remains the weakest of the three. On this store, 13 dependency edges
  produce zero findings, and the check's only measured effect to date has been a
  false-positive class. It is kept because the cost is now one schema property
  rather than a hardcoded set, and removing a check needs its own evidence.
- Not done: no property describes an *inverse* kind (`blocks`/`blocked_by`), and
  `symmetric` does not imply `successor` — `contradicts` declares both. Coupling
  them would make `relates_to` traversed backwards, which changes retrieval for
  every existing store.
