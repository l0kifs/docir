---
created: '2026-07-30'
description: The command exists to catch schema edits before they reach a write; this
  is the most likely schema error and it passes.
id: issue-2b28fd8b1dfa
owner: maintainer
related:
- issue-b47a1203baa2
- issue-40d1792bc9f9
status: resolved
tags:
- schema
- material
title: Should `schema validate` check that transition targets name declared statuses?
type: issue
updated: '2026-08-05'
---

**Gap:** issue-b47a1203baa2
**Blocking:** no · **Rank:** 10 · **Answered:** 2026-07-28
**Authority:** repo maintainer (directed the work; the question was never answered separately, so the recorded assumption was acted on)

## Question

Should `schema validate` check that transition targets and `inactive_statuses` name declared statuses? Today a type can validate with no reachable exit from its default status.

## What the system does today

OBSERVED: `statuses: {open: [closd], closed: []}`, `inactive_statuses: [done]` → `{"valid":true}`. The eventual error, `invalid transition 'open' -> 'closed'`, names a status that IS declared and points at the write rather than the schema. Evidence: schema_loader.py:142-192, schema.py:97-117.

## Proposed answer

Reject unknown transition targets and inactive statuses at load time; warn when a non-inactive status has no outgoing transitions.

## Why it matters

The command exists to catch schema edits before they reach a write; this is the most likely schema error and it passes.

## Answer

Yes to the rejections, no to the warning. Undeclared transition targets, undeclared `inactive_statuses` entries and an undeclared `default_status` are now rejected at load time, with a message naming the declared statuses so it points at the schema. The dead-end warning was implemented and then removed on evidence: it fires on 5 of the 15 shipped types, every one a correct terminal state for a document that stays live. Shipping it would repeat issue-40d1792bc9f9 — a warning that fires on the product's own defaults. See issue-b47a1203baa2 resolution.

## Assumption if unanswered

WAS: the shallow check is an oversight. Confirmed for the status-name checks; the dead-end check turned out not to be an oversight but a rule that cannot be stated correctly with what the schema knows.

---

Migrated from the discovery question queue (Q-010); the queue itself now lives in this store.
