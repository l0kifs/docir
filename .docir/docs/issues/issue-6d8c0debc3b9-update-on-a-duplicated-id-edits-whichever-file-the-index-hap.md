---
code:
- src/docir/modules/documents/application/services/document_service.py
code_baseline:
  src/docir/modules/documents/application/services/document_service.py: 073e8fa4971f
created: '2026-09-23'
description: update, archive and unarchive act on one of two files claiming an id
  without saying which; nothing is lost, but the edit lands somewhere the caller did
  not choose.
id: issue-6d8c0debc3b9
owner: maintainer
related:
- adr-3cfa867c8537
status: open
tags: []
title: update on a duplicated id edits whichever file the index happened to keep,
  silently
type: issue
updated: '2026-09-23'
---

## What is wrong

`docir update <id>` against an id two files claim writes to whichever file the index holds, and
says nothing about the choice. The index keeps one row per id — `reindex` walks `scan()` in
sorted path order and `save` upserts, so the last file wins — so the edit lands on one of two
documents by an accident of filename ordering.

`archive` and `unarchive` share the path and the choice.

## What it does not cost

Verified across every write that could clobber the other claimant:

| write | result |
|---|---|
| `--set-description` | edits the index-held file; the copy keeps its own |
| `--set-title` to *exactly* the other file's title | succeeds and the path **does not change** — the write path keeps the filename, so the rename cannot collide |
| `--type` across directories | moves one file, leaves the other where it is |
| `archive` | frontmatter only, no move |

After each: both files on disk, both bodies intact, and `docir check` still reporting
`duplicate-id` as an **error**. Nothing is lost and the state stays loudly reported, which is
exactly what [[issue-bfa5d4331c35]] destroyed on the delete path — there the index row went
with the file, the duplicate scan then found one file, and `check --strict` exited 0.

So this is a usability defect, not corruption: the edit lands somewhere the caller did not
choose, and the only sign is that the change is not where they expected it.

## Why the delete guard is not simply extended here

Measured on this store (247 documents): a warm write is about **1 ms** and the `scan()` the
guard needs is **40 ms** warm, 210 ms cold. Same absolute cost as on `delete`, opposite
verdict — `delete` is run a handful of times in a corpus's life and its damage is
unrecoverable, while `update` is what an agent runs dozens of times a session, to reach a state
`check` already reports as an error with nothing at stake. A 40x tax on the hot write path to
detect something already being shouted about is the wrong trade. The reasoning is in
[[adr-3cfa867c8537]].

The cheap pre-check does not work either: comparing the file count against the index row count
misses a duplicate whenever the index is stale in the opposite direction by the same amount.

## The route worth taking, if this is worth closing

Stop paying per write. `reindex` already walks every file in sorted path order and is the one
place in the system that **sees** the second claimant before discarding it — it could record
the collision, and every write would then read a column instead of the filesystem.

That is an index schema change (a migration, and a new column or table), so it needs its own
decision, and it would also give `check` a cheaper `duplicate-id` scan than the one it pays for
today. Both halves argue for doing it once, deliberately, rather than bolting a scan onto each
write.

## Until then

`docir check` reports the collision as an error and `docir check --fix` repairs it, re-issuing
all but one id and renaming the file to match. Repair first, then edit. The `delete` refusal
already names that path; `update` does not.
