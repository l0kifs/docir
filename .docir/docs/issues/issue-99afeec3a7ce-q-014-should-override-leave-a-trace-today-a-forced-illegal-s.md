---
created: '2026-07-30'
description: 'Coverage checklist: ''who can override a rule, and is the override audited?'''
id: issue-99afeec3a7ce
owner: maintainer
related:
- issue-0783d236d565
status: resolved
tags:
- schema
- material
title: Q-014 — Should `--override` leave a trace? Today a forced illegal status transition
  is…
type: issue
updated: '2026-07-30'
---

# Q-014 — Should `--override` leave a trace? Today a forced illegal status transition is…

**Gap:** GAP-014 · **Also resolves:** — · **Audience:** repo maintainer
**Blocking:** no · **Rank:** 14 · **Asked:** 2026-07-29 · **Answered:** 2026-07-29
**Authority:** repo maintainer (chose from three options presented with trade-offs)

## Question

Should `--override` leave a trace? Today a forced illegal status transition is indistinguishable from a legal one.

## What the system does today

document_service.py:324-329 — status changes, nothing records that a Tier 0 rule was bypassed.

## Proposed answer

Record it in frontmatter, or drop the flag and require an explicit two-step transition through a legal intermediate.

## Why it matters

Coverage checklist: 'who can override a rule, and is the override audited?'

## Answer

Yes to a trace, no to a record: warn loudly, store nothing. The escape hatch is deliberate and stays; what was missing was telling the operator, at the moment of the bypass, which rule they broke. An `overridden:` frontmatter field was rejected — no actors to attribute it to (ADR-0003), git already records the status change, and it would be permanent schema surface. Dropping the flag was rejected too: a document stranded by a schema change would have no path out but hand-editing, which the GAP-016 contract forbids. See GAP-014 resolution.

---

Migrated from the discovery question queue (Q-014); the queue itself now lives in this store.
