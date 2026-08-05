---
created: '2026-07-30'
description: A user rebuilding after a hand-edit that broke frontmatter is told the
  rebuild succeeded.
id: issue-5f979576ef7d
owner: maintainer
related:
- arch-0a3c2d6d54a6
- issue-6817ed1851e2
status: resolved
tags:
- integrity
- material
title: '`reindex` silently skips unparseable files and reports the rebuild as a success'
type: issue
updated: '2026-08-05'
---

**Class:** misleading · **Severity:** material
**Flow:** arch-0a3c2d6d54a6 · **Step:** reindex over a corpus containing a malformed file
**Question:** None · **Frequency:** any reindex following a bad hand-edit — the scenario reindex exists for

## Finding

`reindex` silently skips files that fail to parse and reports only `documents_indexed`, so a partial rebuild is indistinguishable from a complete one.

## What happens today

`scan()` swallows ValidationError and continues (markdown_store.py:58-62). `ReindexResult` has no skipped/failed count.

## Impact

A user rebuilding after a hand-edit that broke frontmatter is told the rebuild succeeded. The document is simply absent from retrieval.

## Proposed default

Add `documents_skipped` to ReindexResult and print it; the data is already available via `find_malformed()`.

## Resolution

FIXED 2026-07-29, as proposed. `ReindexResult.documents_skipped` counts files that would not parse (from the existing `find_malformed()`), it is in the JSON, and a non-zero count also prints a stderr warning naming `docir check` as the next step. The agent guide now tells agents to read the field. THE FINDING UNDERSTATED ONE CASE AND OVERSTATED ANOTHER — both found by running it: (a) with an index already present, a broken file did produce a signal, but a *misleading* one: `documents_removed: 1`, which reads as "a file was deleted" rather than "a file on disk is unreadable". Not silent, but pointing the wrong way. (b) on a fresh clone the count is `documents_removed: 0, documents_indexed: 1` for two files on disk — genuinely no signal, and this is the worse case because it is exactly where the agent guide tells agents to run `reindex`. Attribution verified by removing the count: two of the three new tests fail. NOTE for issue-6817ed1851e2: this makes "reindex then check" a workflow that can be trusted for *parse* failures. It does nothing for a hand-edit that parses but violates Tier 0 — an unregistered tag or an undeclared status — which `check` still does not detect. The hand-editing contract cannot promise verification until that is closed.

## Actors affected

- repository maintainer

## Evidence

- `src/docir/platform/filesystem/markdown_store.py:51-62`
- `src/docir/modules/documents/application/services/maintenance_service.py:26-33`

---

Migrated from the discovery gap register (GAP-022); the register itself now lives in this store.
