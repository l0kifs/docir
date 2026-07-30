---
created: '2026-07-30'
description: A command whose entire purpose is "check an edit before it reaches a
  write" (app.py:138) passes the most likely schema error, and the eventual message
  misdirects.
id: issue-b47a1203baa2
owner: maintainer
related:
- adr-2a3f625bb2f8
- arch-90c90751344f
- ref-1509d5dbb4c3
status: resolved
tags:
- schema
- material
title: GAP-010 — `schema validate` does not check that transition targets or `inactive_statuses`
  are…
type: issue
updated: '2026-07-30'
---

# GAP-010 — `schema validate` does not check that transition targets or `inactive_statuses` are…

**Class:** misleading · **Severity:** material · **Confidence:** observed
**Flow:** FLOW-004 · **Step:** docir schema validate
**Question:** Q-010 · **Frequency:** any hand-edited schema with a typo — the case the command exists for

## Finding

`schema validate` does not check that transition targets or `inactive_statuses` are declared statuses, so a type can pass validation with no reachable exit from its default status.

## What happens today

OBSERVED. `statuses: {open: [closd], closed: []}` plus `inactive_statuses: [done]` returns `{"valid":true}`. The failure appears later as `invalid transition 'open' -> 'closed'` — naming a status that IS declared, which points the reader at the write instead of at the typo in the schema.

## Impact

A command whose entire purpose is "check an edit before it reaches a write" (app.py:138) passes the most likely schema error, and the eventual message misdirects. Documents can be created in a state with no legal exit.

## Proposed default

In `_parse_type`, reject transition targets and `inactive_statuses` not present in the type's declared status set; warn when a non-inactive status has no outgoing transitions.

## Resolution

FIXED 2026-07-28 — the rejections, not the warning. `_parse_type` now rejects any status name the type does not declare: a transition target, an `inactive_statuses` entry, and `default_status` (which was unchecked too, and would have failed every `add` of that type). The message names the offending value and lists the declared statuses, so it points at the schema instead of at the write. PROBE-12 replayed: the typo'd schema now exits 3 with "type 'ticket' status 'open' transitions to undeclared status(es) 'closd'; declared: closed, open" where it returned `{"valid":true}`. THE PROPOSED WARNING WAS BUILT AND THEN DROPPED, on evidence. "Warn when a non-inactive status has no outgoing transitions" fires on **5 of the 15 shipped types** — `release_note.published`, `postmortem.published`, `experiment.complete`, `hypothesis.supported`, `obligation.breached` — and every one is a correct terminal state for a document that stays live and relevant. Marking them inactive to silence it would be worse: it would hide published postmortems from the default read path. That is GAP-008 exactly, two commits after fixing it: a warning that fires on the product's own defaults, which teaches users to ignore the command. The heuristic is not merely noisy, it is wrong — "terminal" and "closed" are different properties. Recorded here rather than shipped, and noted in the `schema validate` docstring so it is not rebuilt naively. The "every state has an exit" coverage-checklist item is therefore NOT met, deliberately. A rule that could tell a missing transition from an intended terminal state would need to know the type's intent, which nothing in the schema expresses.

## Actors affected

- repository maintainer

## Evidence

- `src/docir/modules/documents/infra/schema_loader.py:142-192`
- `src/docir/modules/documents/domain/schema.py:97-117`
- `ref-1509d5dbb4c3 (discovery probe log)`

---

Migrated from the discovery gap register (GAP-010); the register itself now lives in this store.
