---
code:
- src/docir/modules/documents/domain/value_objects/identifiers.py
- src/docir/modules/documents/application/services/id_generator.py
- src/docir/modules/documents/domain/services/store_format.py
code_baseline:
  src/docir/modules/documents/application/services/id_generator.py: bee108aec57f
  src/docir/modules/documents/domain/services/store_format.py: e47b04e30ed3
  src/docir/modules/documents/domain/value_objects/identifiers.py: 29ed04113c95
created: '2026-09-24'
description: Why id_style chronological mints eight hex of unix seconds plus four
  random, why it keeps the random shape, and why it raises the store format to 3 instead
  of hiding behind a new key.
id: adr-0bb509bd3a19
owner: maintainer
related:
- adr-36d6156ffab9
- adr-ab4598c6f707
status: accepted
tags:
- integrity
- schema
- cli
title: 'Chronological ids: a random token led by the creation second'
type: decision
updated: '2026-09-24'
verified: '2026-09-24'
verified_code:
  src/docir/modules/documents/application/services/id_generator.py: bee108aec57f
  src/docir/modules/documents/domain/services/store_format.py: e47b04e30ed3
  src/docir/modules/documents/domain/value_objects/identifiers.py: 29ed04113c95
verified_content: 9d4ff3a40efd
---

## Context

A store had two id styles and each cost something the other did not. `random` is
collision-resistant across branches, but its twelve hex chars are noise: a type's
directory, sorted by name — how `ls`, a file tree and a code review list it — comes
out in no order at all. `sequential` sorts, and two branches cut from one base each
mint the same number, which `duplicate-id` finds only after the merge.

Nothing about a random token needs all 48 of its bits to be random. A collision
between branches needs two documents minted in the same second *and* the same tail.

## Decision

**`id_style: chronological`**, selectable schema-wide, per type, and through `docir
init --id-style chronological`. The suffix is the creation second as **eight
fixed-width lowercase hex chars**, then **four random hex chars** —
`adr-6ab51e1481ab`. For equal-width lowercase hex, lexicographic order is numeric
order, so a type's files sort by creation time; the width holds unix seconds until
2106 and the builder refuses a second outside it rather than widening silently.

The second comes from the injected `Clock` (a new `now()` beside `today()`), read in
`IdGenerator` and passed into `DocId.build_chronological`, so the domain stays free
of a clock and a test pins the exact prefix. A local collision retries under the
budget `random` already had.

Only sixteen bits are random, so this is weaker than `random` across branches: a
clash needs the same second and the same tail, rare by hand and plausible for bulk
scripted adds on two branches at once. `duplicate-id` still finds it, and the
`check --fix` re-issue keeps the old id's second and draws a new tail, so the
repaired file stays where it sorted instead of moving to the moment of the repair.

Neither default moves. `init` still writes `random`, and a schema with no
`id_style:` still mints `sequential`.

## The shape is a random token's, on purpose

Twelve lowercase hex chars is exactly what `random` mints, so every reader already
parses it — `DOC_ID_RE`, mention scanning, the publisher's id shape — and the
guards keyed on `looks_random` treat it as a token rather than a counter.

That matters because a chronological suffix is all decimal digits whenever its
second and its tail happen to be (`682511900123`).
Read as a counter it would push the type's next sequential id to twelve digits the
day a store switched styles. Both counter paths — `reindex` restoring
`id_sequences`, and `add --id` raising it past an adopted id — already decide by the
**type's configured style** first and the suffix shape second; a chronological type
never touches the counter. Tests pin both with an all-digit suffix.

## Compatibility: store format 3

`id_style` is an existing key given a value older loaders reject, which is the case
[[adr-36d6156ffab9]] reserves the floor for. Measured against the published 0.29.0
([[adr-ab4598c6f707]]): a store declaring `store_format: 3` is refused on every
command with `declares store format 3; this docir understands up to 2`, and `doctor`
reports `store-from-newer-build`. A build before 0.27.0 ignores the floor and stops
on `schema 'id_style' must be one of: sequential, random`. The documents themselves
are not the problem: the same store switched back to `random` reindexes, queries,
gets and passes `check --strict` and `doctor --strict` on 0.29.0.

So `init --id-style chronological` writes `store_format: 3` itself, and a schema
edited by hand gets `store-format-undeclared` until `check --fix` records it.

## Alternatives rejected

**A new key beside `id_style: random`** — the first rule of [[adr-36d6156ffab9]]
would have an older build ignore it and keep minting random ids. Rejected because the
failure it trades for is silent: a teammate on an old build mints unordered ids into
a directory everyone else believes sorts, and nothing reports it. A refusal that
names the upgrade is the better failure for a property the whole team relies on.

**A full timestamp (milliseconds, or a ULID).** Longer ids than every other style,
and a new shape every reader would have to learn. Second precision orders what
people create by hand; documents minted in one second keep a random relative order.

## Consequences

- A team switches a store only after every member, and every repository reading it
  as a peer, runs a docir that reads format 3. The skill, the `init` docstring and
  README say so where an adopter reads them.
- Switching an existing type orders only the ids minted afterwards; earlier random
  ids keep their place, since an id is never re-minted.
- The order is the minting machine's clock. A skewed clock mis-orders its own
  documents and cannot make two ids collide more often than the tail allows.
