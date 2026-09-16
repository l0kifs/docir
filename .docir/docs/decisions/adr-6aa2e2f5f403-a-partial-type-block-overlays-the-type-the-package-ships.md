---
created: '2026-09-15'
description: 'An inline types: entry missing prefix/statuses/default_status is folded
  into the resolved type key by key instead of replacing it, so a store can set one
  property of a core or profile type without pinning the rest.'
id: adr-6aa2e2f5f403
related:
- adr-bc45b0bb1023
status: accepted
tags:
- schema
title: A partial type block overlays the type the package ships
type: decision
updated: '2026-09-15'
---

## Context

`docs-schema.yaml` merges `core -> profiles -> inline`, and the merge was
wholesale per type name: an inline `types:` entry replaced the resolved type
rather than adjusting it. A partial block was a load error — `type 'decision'
must define a string 'prefix'`.

That is fine while inline types are *new* types, which is what they were for.
It stops being fine the moment a store wants to change **one property** of a
type the package ships. adr-bc45b0bb1023 added `max_body_chars`, and the two
types this corpus would want it on — `decision` from the core, `issue` from the
`software` profile — could not have it without restating both types in full.

Restating is not a workaround, it is a trap. The inline copy wins forever, so a
later docir that adds a status, changes a cadence or moves a level for those
types never reaches the store. Nothing reports it: `schema-drift` compares the
resolved schema to the index baseline, and the resolved schema does not move —
that is exactly what the inline copy guarantees.

## Decision

**A type block that cannot stand alone is read as an overlay.**

"Cannot stand alone" is defined by the three keys the loader already requires:
`prefix`, `statuses`, `default_status`. A block carrying all three is a whole
declaration and **replaces** the type, as every fragment always has. A block
missing any of them is folded into the resolved type key by key.

```yaml
profiles: [software]
types:
  decision:
    max_body_chars: 8000     # everything else stays whatever the core says
```

Three properties hold it up.

**Strictly additive.** A partial block is a load error today, so no schema that
currently loads changes meaning. That is the whole compatibility argument, and
it is why the rule keys on completeness rather than on, say, always merging: a
store that restates `issue` without `inactive_statuses` is saying `resolved`
should be visible, and inheriting the profile's value back would overrule a
choice it made on purpose.

**One level deep.** `statuses:` in an overlay replaces the whole status mapping
rather than adding to it. A per-status merge could not express *removing* one,
and a status the base declares that the overlay does not is exactly what a store
re-grammaring a type means to drop.

**Parsed once, at the end.** The merge accumulates raw specs and runs
`_parse_type` over the merged result, so an overlay reaches the same validation
a declaration does: a `default_status` inherited from the base must still name a
status the overlay's own `statuses` declares. A second validation path is how
two commands come to disagree about whether a schema is valid.

**An overlay of a type nobody declares is refused**, naming what is declared at
that point. The usual cause is a typo or a profile that is not enabled, and both
of those would otherwise be silent: a half-type, or a key that configures
nothing.

## Consequences

- Both spellings stay available, and they mean different things. Overlay to
  adjust a type the package owns; restate to take ownership of it, accepting
  that it stops tracking the package.
- This store overlays `decision` and `issue` with `max_body_chars: 8000` — four
  lines, and both types keep inheriting their statuses, levels and cadences.
- The error for a partial block naming an unknown type lists the types declared
  so far, because "did you enable the profile?" is the answer more often than
  "did you misspell it?".
- Verified by injection: making the overlay never happen, making a complete
  block overlay too, and accepting an unknown overlay each fail their own tests
  — the second breaks 59, which is the compatibility guarantee doing its job.
