---
created: '2026-07-30'
description: '"Knows what''s stale" is one of six rows in the README''s comparison
  table (README:44) and one of four bullets in "The model".'
id: issue-b4f441c7210f
owner: maintainer
related:
- adr-bd7c4f3c5764
- arch-0a3c2d6d54a6
- issue-330738a57cb6
status: resolved
tags:
- staleness
- material
title: 'Staleness is detected and never routed: `owner` reaches one `check` message
  and nothing else'
type: issue
updated: '2026-08-05'
---

**Class:** missing · **Severity:** material
**Flow:** arch-0a3c2d6d54a6 · **Step:** acting on staleness
**Question:** issue-330738a57cb6 · **Frequency:** continuous once any document passes its cadence (365d default)

## Finding

Staleness is detected and never routed. `owner` is stored and interpolated into one `check` message; there is no notification, no `--owner` filter, no "documents I own" view, no scheduled reminder.

## What happens today

A stale document stays stale until somebody happens to run `docir check` and read past the orphan noise.

## Impact

"Knows what's stale" is one of six rows in the README's comparison table (README:44) and one of four bullets in "The model". The detection is real; the loop that would make it change anything is absent. adr-bd7c4f3c5764 justifies not auto-detecting staleness — it does not address delivering it to the named owner.

## Proposed default

Add `docir query --owner <name>` and `--stale` as first-class filters. That is the smallest thing that turns the data into a workflow, and it needs no new subsystem.

## Resolution

FIXED 2026-07-28, as proposed and no further. `docir query --owner <name>` and `--stale` are first-class filters; together they are one steward's review queue, and `docir update <id> --verified` clears an entry. Verified end-to-end on the real CLI through the whole loop, including that `--verified` empties the queue. The two filters live in different layers on purpose. `owner` is a column, so it is a SQL predicate on `DocumentFilter`. Staleness is *derived* — clock minus the document's reference date against the type's `review_days` — and the index stores neither the clock nor the schema, so `DocumentFilter` deliberately has no `stale` field and the service filters after the query. Pushing it into SQL would mean denormalising a value that changes every day without a write. ORDERING IS LOAD-BEARING: the stale filter runs *before* the limit, so `--stale --limit 10` means ten stale documents rather than the stale ones among the first ten. The fixture corpus is built so the naive order fails loudly — the newest document sorts first and is not stale, so a limit applied first returns nothing at all. Pinned by test_stale_is_filtered_before_the_limit and confirmed by reverting the order. NO NEW SUBSYSTEM, deliberately: no notifications, no scheduler, no assignment workflow. adr-bd7c4f3c5764's argument that staleness must be honest human re-verification applies to the delivery mechanism too — an automated nag that a bot can clear is not a human vouching for content. The agent guide now says stale means "nobody has vouched recently", not "wrong", and that `--verified` must never be stamped on a document the agent has not actually read.

## Actors affected

- document owner / steward
- repository maintainer

## Evidence

- `src/docir/modules/documents/domain/services/graph_checks.py:100-102`
- `src/docir/modules/documents/domain/entities/document.py:37`

---

Migrated from the discovery gap register (GAP-011); the register itself now lives in this store.
