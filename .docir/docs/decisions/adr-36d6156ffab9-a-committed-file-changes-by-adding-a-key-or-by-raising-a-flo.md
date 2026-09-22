---
code:
- src/docir/modules/documents/domain/services/store_format.py
- src/docir/modules/documents/infra/schema_loader.py
- src/docir/platform/filesystem/schema_store.py
- src/docir/entry_points/doctor.py
code_baseline:
  src/docir/entry_points/doctor.py: ce032a47b5e6
  src/docir/modules/documents/domain/services/store_format.py: eb89d11244ff
  src/docir/modules/documents/infra/schema_loader.py: 4cbd9ed6460b
  src/docir/platform/filesystem/schema_store.py: 64b0230bb494
created: '2026-09-16'
description: Why new meaning goes in a new key older builds ignore, why the fallback
  is a store_format floor read before the schema resolves, and why neither reaches
  a build already installed.
id: adr-36d6156ffab9
owner: maintainer
related:
- adr-49bb8cc48938
- adr-6aa2e2f5f403
- adr-ab4598c6f707
- issue-c30895cc62a3
- adr-bd3a820cc57a
- issue-d891ab5501e6
status: accepted
tags:
- cli
- integrity
- persistence
title: A committed file changes by adding a key, or by raising a floor
type: decision
updated: '2026-09-22'
verified: '2026-09-22'
verified_code:
  src/docir/entry_points/doctor.py: ce032a47b5e6
  src/docir/modules/documents/domain/services/store_format.py: eb89d11244ff
  src/docir/modules/documents/infra/schema_loader.py: 4cbd9ed6460b
  src/docir/platform/filesystem/schema_store.py: 64b0230bb494
verified_content: 328a46956df1
---

Two file changes shipped a release apart, against the same store, and only one of them
broke. The difference was not size; it was whether the new meaning arrived under a new
name. That is the rule, and the floor below is what covers the cases where it cannot.

## The measurement

`docir==0.26.0`, pointed at a store this build wrote:

- Frontmatter gained `code_baseline:` ([[adr-49bb8cc48938]]). It reindexes 216 of 216
  documents, skips none, and `doctor --strict` and `check --strict` both exit 0. An
  unrecognised key is ignored.
- `docs-schema.yaml` gained a partial `types:` block ([[adr-6aa2e2f5f403]]). Every command
  exits 3 on `type 'decision' must define a string 'prefix'` — the schema resolves before
  anything opens, so nothing in the corpus is reachable ([[issue-c30895cc62a3]]).

Same store, same release, opposite outcomes.

## First rule: new meaning gets a new key

An unknown *top-level* key in `docs-schema.yaml` is ignored by the released loader —
measured the same way, by adding one and watching `query` answer. So the overlay could have
been `type_overlays:` and broken nothing, where `types:` carrying a block that is invalid
under the old rule could not.

This is the only protection that reaches a build somebody has already installed. Nothing
docir ships later arrives in that loader; the shape of the file is the one thing that does.
It also costs nothing, which is why it comes first rather than second.

## Second rule: when the meaning cannot be new, record the floor

Some changes have nowhere additive to go — a key whose *absence* the new build reads as
something other than unknown, or a value an old build would act on wrongly rather than
ignore. Those record a floor.

`store_format:` sits in `docs-schema.yaml` and is read before the schema is resolved. A build
below it stops naming the format the store needs, the format it understands, and the upgrade
— instead of a parse error naming a field nobody removed.

Written by the feature that raises it, never by hand: a floor a human has to remember is a
floor that records the release *after* the one that needed it. `check` derives what the file's
contents need and compares; `check --fix` writes the line, textually, so the comments the file
exists to carry survive.

## What a floor cannot do

The same measurement cuts both ways. Every build published before 0.27.0 ignores `store_format:` exactly
as it ignores any unknown key, so a floor earns nothing on those builds — it starts protecting
a reader only once a build that carries it, 0.27.0 or later, is installed.

That is not an argument against it — it is why the first rule is first, and why
[[issue-c30895cc62a3]] could not be repaired retroactively for anyone on 0.26.0. A floor is a
promise to future readers. The key shape is the only promise to current ones.

## The precedent, and the half that never got it

The index has had this since [[adr-fb938175f72a]]'s peer reads: `_peer_schema_status`
compares one revision rather than guarding each column, on the stated grounds that guarding
per column "did work and did not scale — the next migration reintroduces the bug by
default", and `index-from-newer-build` answers the other direction by naming the version and
the remedy.

The committed half — the schema file and the frontmatter — never got either. Two releases
running then shipped an unannounced floor, and [[adr-ab4598c6f707]]'s check is what found
the second one, from inside the change it was meant to protect.

## What counts as raising a floor

A new *required* key. An existing key given a shape the old rule rejects. A value whose
absence an older build reads as anything but unknown.

Not: a new optional key, which rule one already covers; a new finding kind, which an older
`check` simply never emits; a new command or flag, which lives in the package rather than in
the store.

## Why an integer, not a version

`min_docir:` was the obvious spelling and does not work here. This repository bumps its
version *at* release, so main always carries the last published number: a change that needs
the next release would write a floor naming a version that does not exist yet, and the build
writing it would be locked out of its own store the moment it read it back.

An integer avoids the question. `store_format:` counts formats, not releases, and a build
declares the highest it understands — the shape the index already uses, where
`_peer_schema_status` compares a migration revision and `index-from-newer-build` reports one.

The cost is that the refusal cannot name a release to install: an older build has no table
mapping format 3 to a version it has never heard of. It says the two numbers and "upgrade
docir", which is what its index counterpart has always said.

## The version key adr-bd3a820cc57a rejected

[[adr-bd3a820cc57a]] lists "a `schema_version:` key" among the moves that were "all available and
all wrong for this project", and [[issue-d891ab5501e6]] rejects that and pinning a store to a
docir version in the same breath. This is a version key in that file, and it does pin. The
objections are worth answering rather than stepping around.

## They answer a different question

Those two are about **drift**: the file does not change and its meaning does, because the core and
the profiles are compiled into the package and re-resolved on every command. Their objection to a
key in the file is exact — it is hand-edited, so it drifts from what the file says, and it
describes the file while the change arrives from the package. A key cannot track a change that
never touches the file.

`store_format:` describes the file's own **shape**, which moves only when somebody edits it. It is
derived from the constructs in use, written by `check --fix` and never maintained by hand, so the
drift the objection predicts has nowhere to come from — and `check` reports the moment the
declaration and the contents disagree, which is the guarantee a hand-maintained key could not give.

## And it pins the reader, not the store

"Pinning a store to a docir version" was rejected for trading a silent change for a hard stop that
leaves the corpus behind on an old release. This does the opposite of that: it constrains nothing
about which docir a store may use going forward, and every current build is unaffected. It names
the minimum a *reader* needs, so a build that cannot parse the file stops with a sentence about
versions instead of a parse error about a key nobody removed.

What would overturn it: a floor that ever has to be written or maintained by hand. Then
[[adr-bd3a820cc57a]]'s objection lands squarely, and this becomes the thing it warned about.
