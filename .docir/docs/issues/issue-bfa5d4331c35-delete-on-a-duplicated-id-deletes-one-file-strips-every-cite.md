---
code:
- src/docir/modules/documents/application/services/document_service.py
code_baseline:
  src/docir/modules/documents/application/services/document_service.py: f57b891a1bfb
created: '2026-09-23'
description: Every step of delete reads the index, which holds one row per id, so
  a delete against two files claiming one id acts on a file nobody chose and breaks
  edges to the survivor.
id: issue-bfa5d4331c35
owner: maintainer
related:
- adr-3cfa867c8537
status: resolved
tags: []
title: delete on a duplicated id deletes one file, strips every citer's edge, and
  drops the other from the index
type: issue
updated: '2026-09-23'
---

## What is wrong

`docir delete <id>` does not see the state `check --strict` reports as `duplicate-id`. Against
an id two files claim — what a merge of two branches on `--id-style sequential` produces, or a
copied file — it does three things, and each is silent.

**1. It acts on whichever file sorts last.** `reindex` walks `scan()` in sorted path order and
`save` upserts by id, so each later file overwrites the earlier one's row and the index holds
one. The caller is never told there was a choice.

**2. `--force` strips the edge from documents citing the file it is not deleting.** Edges are
addressed by id and both files answer to it, so `incoming(doc_id)` returns citers of both. Their
frontmatter is rewritten to drop an edge whose target is still on disk.

**3. The surviving file drops out of the index.** `documents.delete(doc_id)` removes the only
row, so a file that is still there is invisible to `get`, `query` and `context` — and
`check --strict` exits **0**, because the duplicate-id scan now finds one file and nothing
compares the files against the index.

Without `--force`, the refusal lists citers of both documents as if they cited one.

## Why nothing catches it afterwards

Measured on a store damaged by the reporter's own script:

| moment | what reports it |
|---|---|
| right after the delete | `doctor` → `index-behind-files`, a warning that already existed |
| after any `reindex` | nothing — `doctor` clean, `check --strict` exit 0 |
| in CI | never: the job runs `reindex` → `doctor --strict` → `check --strict`, so it heals the index before it looks |
| with the daemon | never: the watcher reindexes on the next change under `docs/` |

The stripped edge survives all four. `related: []` is a valid state and the only trace is an
`orphan` warning indistinguishable from a document nobody has linked yet.

## Resolution

FIXED — [[adr-3cfa867c8537]]. `delete` refuses an id more than one file claims, `--force`
included, naming the files and the repair. The count comes from `scan()` rather than the index,
which cannot answer the question, and the refusal runs before the unit of work opens so nothing
is read or written on the way to it.

Prevention only, because nothing can find the damage after the fact; `git log -p` on the citing
document is the only recovery for an edge already stripped.

Five guards in `tests/modules/documents/test_merge_safety.py`, verified by removing the call:
the three that assert the refusal fail, and the two that pin what did not move — an ordinary
delete, and a forced delete against an unambiguous id still stripping edges — pass either way.
The reporter's reproduction script now exits 0.

`update` against a duplicated id makes the same arbitrary choice and is deliberately left
alone. Verified across every write that could clobber: a title change keeps the filename (so it
cannot be renamed onto the other claimant), `--type` moves one file and leaves the other, and
`archive` touches frontmatter only. Both bodies survive each and `check` keeps reporting
`duplicate-id` as an error. What is left is a usability defect — the edit lands on one of two
documents and nobody says which — priced at 40x the warm write to detect. The reasoning is in
[[adr-3cfa867c8537]].

Reported as GitHub #27.
