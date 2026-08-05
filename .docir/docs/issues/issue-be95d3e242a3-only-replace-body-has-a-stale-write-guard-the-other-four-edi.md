---
created: '2026-07-30'
description: The guard exists and is computed; applying it to one of five edit modes
  is a decision nothing records.
id: issue-be95d3e242a3
owner: maintainer
related:
- adr-d3e3616400bf
- arch-3e305bc76ff0
- issue-389dc5dac58a
status: resolved
tags:
- persistence
- material
title: Only `--replace-body` has a stale-write guard; the other four edit modes have
  none
type: issue
updated: '2026-08-05'
---

**Class:** unstated · **Severity:** material
**Flow:** arch-3e305bc76ff0 · **Step:** two concurrent updates to the same document
**Question:** None · **Frequency:** unknown; requires concurrent writers, which the daemon serializes but does not make conflict-free

## Finding

Only `--replace-body` has a stale-write guard. Two concurrent metadata patches to the same document silently last-write-wins.

## What happens today

The content_hash comparison is computed on every update (document_service.py:136) but consulted only in the `replace_body` branch (:374).

## Impact

The guard exists and is computed; applying it to one of five edit modes is a decision nothing records. Coverage checklist: 'entity changed state between validation and commit'.

## Proposed default

State the intent: either extend the guard to all metadata patches, or document that patches are intentionally last-write-wins because they are field-scoped and commutative.

## Resolution

STATED 2026-07-29, not changed — the scoping turned out to be correct and the gap was the missing rationale (which is what `class: unstated` claims). Traced and verified rather than reasoned about: every edit is applied to `base`, the document *as it is on disk*, so a metadata patch or a section edit composes with an out-of-band change; only `--replace-body` discards `base.body`, so only it can lose data to a divergence. Demonstrated on a file carrying a hand-written paragraph the index did not know about: `--set-title` renamed the document and the paragraph survived; `--append-section` added its section and the paragraph survived; `--replace-body --force` refused. Extending the guard would reject writes that lose nothing. TWO CORRECTIONS TO THIS RECORD, both from reading the code rather than the summary: (a) it is a *divergence* check (index vs disk), NOT optimistic concurrency control. No caller supplies a version token, so it cannot detect a competing writer at all — it detects a hand-edit or a merge. The finding's framing as a concurrency guard was wrong. (b) the "concurrent metadata patches silently last-write-wins" claim is weaker than stated. The daemon is a single-connection-at-a-time server, so that path has no window; `--no-daemon` does, but 12 trials of two parallel patches to disjoint fields lost 0, because process startup (~0.5s) dwarfs the microsecond window. Contrast issue-389dc5dac58a, which reproduced 6/6 because every process hit the same counter. It is a real but narrow race, not the everyday behaviour the finding implied. Recorded in `update`'s docstring, in CLAUDE.md, and — more durably — as `TestDiskDivergenceScoping`, so a future tidy-up toward "consistency" fails a test rather than a review. The parameter is renamed `stale` -> `disk_diverged`: `stale` already means "past its review cadence" everywhere else in this codebase, and the collision is part of why the guard read as an oversight.

## Actors affected

- AI coding agent

## Evidence

- `src/docir/modules/documents/application/services/document_service.py:136`
- `369-380`

---

Migrated from the discovery gap register (GAP-037); the register itself now lives in this store.
