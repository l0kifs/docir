---
created: '2026-07-30'
description: The fast path silently has different semantics from the full path — deletions
  are invisible to it.
id: issue-c33edcf431fa
owner: maintainer
related:
- arch-0a3c2d6d54a6
status: resolved
tags:
- integrity
- material
title: '`reindex --changed` skips the removal sweep, so deleted documents stay in
  the index'
type: issue
updated: '2026-08-05'
---

**Class:** unstated · **Severity:** material
**Flow:** arch-0a3c2d6d54a6 · **Step:** reindex --changed
**Question:** None · **Frequency:** any use of --changed after a file deletion

## Finding

`reindex --changed` skips the removal sweep entirely, so documents deleted from the filesystem remain in the index and keep being returned by every read path.

## What happens today

maintenance_service.py:166-174 guards the sweep with `if not changed_only`. Neither `--help` nor the README mentions the difference.

## Impact

The fast path silently has different semantics from the full path — deletions are invisible to it. An agent then retrieves a document whose file is gone.

## Proposed default

Document it in `--help`, or make the sweep unconditional (it is a single id-set difference and cheap).

## Resolution

FIXED 2026-07-29 with the second option — the sweep is unconditional — after checking that "cheap" was true rather than assuming it. `scan()` runs in full under `--changed` already (that is where the parsing cost is, and `seen` has to be complete for `_restore_id_sequences`), so the sweep adds one `documents.all()` query and a set difference. What `--changed` actually skips is the *writes*: save, FTS index, embedding recompute. Skipping the sweep was never what made it fast. Confirmed before and after on the real CLI: delete a file, `reindex --changed` → previously `documents_removed: 0` with `query` still listing it and `get` answering for a file that did not exist; now `documents_removed: 1` and gone from every read path. A follow-up `--changed` still reports `documents_indexed: 0`, so the fast path is still fast. Documented as well as fixed, since the two modes reading differently was half the finding: `--help`, the agent guide and CONTRACT.md now all say the sweep runs in both modes. Preferring the code fix over documentation alone was the right call — an option whose only difference is "silently keeps deleted documents" is not a documentation problem.

## Actors affected

- repository maintainer
- AI coding agent

## Evidence

- `src/docir/modules/documents/application/services/maintenance_service.py:166-174`

---

Migrated from the discovery gap register (GAP-021); the register itself now lives in this store.
