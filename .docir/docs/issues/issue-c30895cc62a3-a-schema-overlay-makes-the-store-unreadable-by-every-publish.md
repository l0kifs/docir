---
code:
- src/docir/modules/documents/infra/schema_loader.py
code_baseline:
  src/docir/modules/documents/infra/schema_loader.py: 95c1dd812abc
created: '2026-09-16'
description: A partial type block loads only on an unreleased docir, so every command
  refuses for anyone on the current release — and it has already disabled docir's
  own published-build check.
id: issue-c30895cc62a3
owner: maintainer
related:
- adr-6aa2e2f5f403
- adr-ab4598c6f707
- adr-49bb8cc48938
- adr-36d6156ffab9
- adr-6d4d43d44075
status: resolved
tags:
- cli
- integrity
title: A schema overlay makes the store unreadable by every published docir
type: issue
updated: '2026-09-17'
---

A partial `types:` block loads only on a docir that ships [[adr-6aa2e2f5f403]], which at the
time no release did. This store adopted one in the same commit that added the feature, so the
then-newest published docir, 0.26.0, could not open it at all.

## What refuses, measured

Every command, against a copy of this store, with the release `docir self status` names as
current:

```
DOCIR_HOME=<copy> uvx --from docir==0.26.0 docir --no-daemon get adr-d9e6d5ccd0b4
error: type 'decision' must define a string 'prefix'   # exit 3
```

`context`, `query` and `check --strict` answer the same way. Not a degraded read: the
schema is resolved before anything opens, so nothing in the corpus is reachable — the
refusal [[adr-ab4598c6f707]] defines as the break.

## Why the overlay's compatibility argument does not cover it

[[adr-6aa2e2f5f403]] holds that the change is strictly additive: a partial block is a load
error today, so no schema that currently loads changes meaning. That is true in the
direction it names — a newer loader reading an older file.

The break runs the other way. An older loader reading a newer file was a load error before
and stays one, and no merge rule shipped later can reach a loader already installed. The
feature is additive; adopting it in a committed file is not.

## It has already disabled the check it would be caught by

[[adr-ab4598c6f707]] requires every change to be pointed, in both directions, at a store
the other build created. Since the overlay landed, that run refuses on this store before it
reaches whatever is under test.

[[adr-49bb8cc48938]] hit exactly this: its cross-version run had to be done against a copy
with the two overlay blocks deleted, which is a store no teammate has. A gate that cannot
start is a gate nobody is running, and the next change is likelier to skip it than to
rebuild the workaround.

## The same shape, wider, for an adopter

A store that adopts an overlay stops answering for every teammate who has not upgraded, and
for every repository declaring it a peer. `docir schema validate` says nothing, because the
file is valid for the build validating it — the one build guaranteed not to be the one that
refuses.

## What would close it

Not a rollback; the overlay is the right feature. Candidates, none chosen here:

- A floor recorded in the store, so an older docir refuses with a sentence naming the
  version it needs rather than a field-level parse error about a key nobody removed.
- `docir schema validate` answering which builds can read the file, before the edit is
  committed rather than after a teammate cannot read the store.
- A way to run [[adr-ab4598c6f707]]'s check against a store the published build can open,
  so the gate survives a schema that has moved ahead of the release.

## What shipped, and what it cannot reach

[[adr-36d6156ffab9]] shipped the two rules and this store now declares `store_format: 2`.
`docir check` reports a schema whose contents need a higher floor than it records, `check
--fix` writes the line without touching the file's comments, and a build below a declared
floor stops naming both numbers — verified against a copy of this store set to format 3,
where `doctor` reports `store-from-newer-build` as an error and every read refuses by name.

What no code can undo: 0.26.0 predates the check, so it ignores the line and still fails on
`type 'decision' must define a string 'prefix'`. 0.27.0 is the first published build that reads
both the overlay and `store_format:`, so [[adr-ab4598c6f707]]'s cross-version run against this
store runs unmodified from that release on; against 0.26.0 or older it still has to be done on
a copy with the overlay blocks deleted — which is what any teammate or peer on those builds
sees. That is the cost the ADR records as the
reason the first rule — new meaning in a new key — comes before the floor at all.
