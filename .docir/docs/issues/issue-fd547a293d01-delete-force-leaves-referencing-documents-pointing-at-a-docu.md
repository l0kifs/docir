---
created: '2026-07-30'
description: The graph — the feature that distinguishes docir from a folder of files
  — silently accumulates unresolvable edges, in the canonical files, permanently.
id: issue-fd547a293d01
owner: maintainer
related:
- arch-3e305bc76ff0
- ref-1509d5dbb4c3
- issue-9ed4905e0db8
- issue-0a4ad65b8a70
status: resolved
tags:
- integrity
- material
title: '`delete --force` leaves referencing documents pointing at a document that
  no longer exists'
type: issue
updated: '2026-08-05'
---

**Class:** missing · **Severity:** material
**Flow:** arch-3e305bc76ff0 · **Step:** delete --force, and every later write to a referencing document
**Question:** issue-0a4ad65b8a70 · **Frequency:** every forced delete

## Finding

`delete --force` leaves referencing documents pointing at a document that no longer exists, and nothing ever repairs it. Tier 0 validates only edges supplied in the current call, so the broken edge is rewritten to the canonical file on every subsequent update.

## What happens today

OBSERVED. After `docir delete issue-0001 --force`, adr-0001's file still reads `related: [issue-0001]`. `docir update adr-0001 --set-title X` succeeds and re-persists the broken edge. `docir check` reports it forever; no command fixes it.

## Impact

The graph — the feature that distinguishes docir from a folder of files — silently accumulates unresolvable edges, in the canonical files, permanently.

## Proposed default

Strip the edge from referencing documents as part of the forced delete (the same transaction pattern `tag rm --force` already uses for tags — the machinery exists and is applied to the lesser case).

## Resolution

FIXED 2026-07-28, as proposed. `DocumentService.delete` strips the edge from every referencing document in the same transaction as the delete, and returns their ids; `delete` now reports "deleted X; unlinked from Y" rather than silently rewriting other people's files. PROBE-6 and PROBE-7 replayed against the real CLI: the referencing file reads `related: []`, `check` reports only the (correct) `orphan`, and a later `update` has nothing broken to re-persist. DEVIATION from the proposed pattern, deliberate: `tag rm --force` advances `updated` on the documents it edits, and this does NOT. Staleness records when a human last vouched for the content, and having a link removed from underneath you is not that — the same reasoning `check --fix` already applies. Copying the tag path wholesale would have reproduced issue-9ed4905e0db8, which is open against that path for exactly this. CONSEQUENCE for the test suite, worth noting because it changes what the tests mean: five tests used `delete --force` as a convenient way to *manufacture* a dangling edge, and that route is now closed. They construct it the way it actually arises instead — remove the target's file as a merge from a branch that deleted it would, then reindex — via a `drop_file_of` fixture. The old shortcut had quietly made a merge-safety test not simulate a merge. GAP-007 is now prevented rather than merely recoverable; `check --fix` remains the recovery path for edges broken outside the CLI, which is the only way left to break one.

## Actors affected

- AI coding agent
- repository maintainer

## Evidence

- `src/docir/modules/documents/application/services/document_service.py:190-206`
- `src/docir/modules/documents/domain/services/validation.py:61-66`
- `ref-1509d5dbb4c3 (discovery probe log)`

---

Migrated from the discovery gap register (GAP-007); the register itself now lives in this store.
