---
code:
- src/docir/modules/documents/application/services/store_repairer.py
code_baseline:
  src/docir/modules/documents/application/services/store_repairer.py: 9f1e0f7f7801
created: '2026-09-23'
description: Two branches off one base allocate the same next id; nothing warns before
  the merge, and check --fix picked the survivor by filename whenever both were created
  the same day.
id: issue-9683b4713792
owner: maintainer
related:
- adr-df43aff8bb0d
- adr-39210c34551a
status: resolved
tags: []
title: Sequential id collisions surface only at the merge, and the surviving id was
  decided by filename order
type: issue
updated: '2026-09-23'
---

## What is wrong

Two branches cut from the same base each allocate the next free sequential id. Both are
correct locally, both pass `docir check --strict`, and neither can see the other. The
collision exists from the moment the second branch allocates and surfaces only when it merges.

Reported from a store where two concurrent branches minted `arch-0014`, `plan-0011` and a
decision id each — three collisions in three series from one shared base.

## What already works

`docir check --fix` repairs it: it re-issues one of the two ids, renames the file to match,
leaves `created` untouched, and the store verifies clean afterwards.

## The survivor was a coin flip

The report said `--fix` "picks the surviving id by filename order". The rule was one step
further back, which matters because it changes the fix. `created` was already the primary key.
Three probes on the build before this change:

| `created` | survivor |
|---|---|
| both the same day | the file whose name sorts first |
| established older | established |
| established **newer** | the incoming one — the date overrules the alphabet |

So the documented key worked, and `created` is a **`date`** — it never separates two branches
cut from one base and merged inside a day, which is the shape of nearly every real collision.
The rule silently degraded to filename order exactly where it was needed.

## Resolution

FIXED for the survivor choice — [[adr-39210c34551a]]. Git provenance decides first (the file
with the older add commit keeps the id), `created` is the fallback where there is no history,
and a filename tiebreak now says it could not tell rather than looking authoritative.

The first `subprocess` call to `git` in docir, which is a deliberate exception to
[[adr-1d1eddbb6fbd]]'s precedent and argued there: that precedent is about per-machine answers,
and committed history is shared.

Three guards in `tests/modules/documents/test_merge_safety.py`, each naming the incoming file
`aaa-…` and the established one `zzz-…` so a filename tiebreak hands the id to the wrong
document. Verified by removing the git key: the provenance test fails, the two pinning the
fallbacks pass either way.

## Also resolved: the pre-merge check

[[adr-df43aff8bb0d]] — `docir check --against <ref>` reports ids new on this branch that the
ref already uses, and refuses to be silent about a ref it could not read.

The collision is knowable the moment the second branch allocates — the ids exist on both
sides — and that is while renumbering is still cheap; after the merge, whoever merges second is
repairing a conflict. `check` already held everything needed except the comparison, so it
gained a flag rather than a command.

Six guards in `tests/modules/documents/test_merge_safety.py`. Verified by removing the call:
the three asserting a finding fail, and the three asserting silence — a document the base
already has, a genuinely new id, and no flag at all — pass either way.

## And a smaller one

A store already on `sequential` has no documented path to `random`. There is no command; the
key is per-type (`id_style:` under a type, or the top-level default), and changing it only
affects ids minted from then on — existing ids are never re-minted, since a document's id is
its only address. Worth a sentence in the schema documentation.
