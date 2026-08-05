---
created: '2026-07-30'
description: 'Coverage checklist: "Admin: who can override a rule, and is the override
  audited?" — the override exists, the audit does not.'
id: issue-0783d236d565
owner: maintainer
related:
- adr-90e994d931cc
- arch-3e305bc76ff0
- issue-40d1792bc9f9
- issue-6817ed1851e2
- issue-9cb85759076d
status: resolved
tags:
- schema
- material
title: '`--override` bypasses the transition rules and leaves no trace'
type: issue
updated: '2026-08-05'
---

**Class:** missing · **Severity:** material
**Flow:** arch-3e305bc76ff0 · **Step:** --override on an illegal status transition
**Question:** issue-99afeec3a7ce · **Frequency:** unknown

## Finding

`--override` bypasses the transition rules and leaves no trace. The resulting document is indistinguishable from one that transitioned legally.

## What happens today

Status changes; no marker, no note, no audit field. The status grammar — a Tier 0 hard rule — has an unlogged escape hatch.

## Impact

Coverage checklist: "Admin: who can override a rule, and is the override audited?" — the override exists, the audit does not. git history records that the status changed but not that a rule was bypassed to change it.

## Proposed default

Either record the override in frontmatter (e.g. an `overrides:` note), or drop the flag and require an explicit two-step transition.

## Resolution

DECIDED 2026-07-29 by the maintainer, from three options: warn loudly, store nothing. `--override` keeps working and now prints a stderr warning naming the rule it broke and the legal moves from the current status; `DocumentView.forced_transition` carries the same description over the wire. Nothing is written to the file. WHY NOT AN AUDIT FIELD: docir has no actors or permissions (adr-90e994d931cc), so "who overrode this" has no answer worth storing; git already records the status change; and an `overridden:` field would be permanent schema surface on every type, plus a decision about whether a later legal transition clears it. What was actually missing was not a record but a *signal* — the operator was never told a rule had been bypassed at the moment they bypassed it. WHY NOT DROPPING THE FLAG: a document stranded by a schema change may have no legal path out, and the only remaining fix would be hand-editing `status` — which the issue-6817ed1851e2 contract now explicitly tells people not to do. THE FINDING OVERSTATED THE HOLE. `--override` still calls `validate_status`, so it permits an illegal *jump between declared statuses*, never an undeclared one; it is not a general Tier 0 bypass. Pinned by a test asserting `--override --status invented` still raises. Also pinned: passing the flag on a transition that was legal anyway does not warn — a guard that cries wolf gets ignored, which is the issue-9cb85759076d/issue-40d1792bc9f9 lesson.

## Actors affected

- repository maintainer
- AI coding agent

## Evidence

- `src/docir/modules/documents/application/services/document_service.py:324-329`

---

Migrated from the discovery gap register (GAP-014); the register itself now lives in this store.
