---
created: '2026-07-30'
description: '''Knows what''s stale'' is one of six rows in the README comparison
  table. Detection works; the loop that would make it matter is absent.'
id: issue-330738a57cb6
owner: maintainer
related:
- issue-b4f441c7210f
- adr-bd7c4f3c5764
status: resolved
tags:
- staleness
- material
title: '`owner` is captured and only ever interpolated into a `check` message'
type: issue
updated: '2026-08-05'
---

**Gap:** issue-b4f441c7210f
**Blocking:** no · **Rank:** 13 · **Answered:** 2026-07-28
**Authority:** repo maintainer (directed the work; the question was never answered separately, so the proposed answer was implemented as-is)

## Question

`owner` is captured and only ever interpolated into a `check` message. How is a stale document supposed to reach the person accountable for it?

## What the system does today

No notification, no `--owner` filter, no 'documents I own' view, no reminder. Evidence: graph_checks.py:100-102, document.py:37.

## Proposed answer

`docir query --owner <name>` and `--stale` as first-class filters — the smallest change that turns the data into a workflow.

## Why it matters

'Knows what's stale' is one of six rows in the README comparison table. Detection works; the loop that would make it matter is absent.

## Answer

By pulling, not by pushing. `docir query --owner <name> --stale` is the review queue and `docir update <id> --verified` clears an entry — the smallest change that turns the data into a workflow, with no new subsystem. Notification was considered and deliberately not built: adr-bd7c4f3c5764's reasoning that staleness must be honest human re-verification applies to delivery as much as detection, and an automated nag a bot can clear is not a human vouching for content. See issue-b4f441c7210f resolution.

## Assumption if unanswered

WAS: manual `docir check` is the intended delivery mechanism. Superseded — `query` is, and `check` remains the audit rather than the worklist.

---

Migrated from the discovery question queue (Q-013); the queue itself now lives in this store.
