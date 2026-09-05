---
created: '2026-09-04'
description: Why an absent `verified` falls back to `created` rather than `updated`,
  and why absent is not treated as infinitely stale.
id: adr-fad49eaa4648
owner: maintainer
related:
- kind: refines
  to: adr-bd7c4f3c5764
- issue-6726eabcf871
status: accepted
tags:
- integrity
- schema
title: Staleness ages from creation, never from the last edit
type: decision
updated: '2026-09-05'
---

## Context

adr-bd7c4f3c5764 made staleness data: a per-type `review_days` cadence, an optional `verified`
date, and `today - (verified or updated) > review_days`. The `updated` half of that fallback is
the defect in issue-6726eabcf871: `updated` moves on every edit, so a document nobody had
vouched for left the review queue as soon as anybody wrote in it.

The fallback has to answer "what is the earliest date docir can honestly claim somebody looked
at this?" for a document with no `verified`. `updated` answers a different question — "when was
this file last touched?" — and the two come apart hardest in the document that matters most: the
evidence that an ask is still unanswered is a re-check written into its body. Recording the
silence is what ended the report of it.

## Decision

Staleness ages from a date an edit cannot move. `Document.stale_reference_date()` returns
`verified` when present and **`created`** otherwise; it never reads `updated`.

`created` is the one date the write path sets once and never rewrites — not a retype, not a tag
rename, not `check --fix`, not a body edit. A document with no `verified` therefore enters the
queue exactly one cadence after it was written and stays there until somebody stamps
`docir update <id> --verified`.

The `stale` finding now names the clock it read: *never verified, created <date>* or *verified
<date>*, plus the command that clears it. Without that, a reader who edited a document yesterday
sees it reported as overdue and reads the finding as a bug.

## Alternatives considered

**Age from `verified` alone, treating absent as infinitely stale.** Semantically the cleanest
reading of the queue — a document nobody has vouched for is stale by definition — and it was
measured before being rejected. On this store on 2026-09-05 (196 live documents, 84 carrying a
cadence, 1 carrying `verified`) it reports **83 of 84** documents stale, including ones written
the day before, because the corpus is younger than its shortest cadence. It also makes
`review_days` inert for every unverified document: the cadence never applies, so the queue is
"everything", cannot be worked down, and is indistinguishable from a corpus that has genuinely
rotted. That is issue-40d1792bc9f9 again — a warning that fires on the product's own defaults —
and the same argument the `docir schema validate` dead-end warning was dropped on.

**A second stamp for "I re-checked and it is still unanswered", distinct from `verified`.** This
records the real event, which `created` only approximates, and it is what the reporter's own
workaround does with a date declared in the body. Rejected here as the wrong size of change for
a defect fix: a frontmatter field, a migration, a CLI verb, an MCP argument and a contract
clause, for one workflow. It stays additive — nothing in this decision forecloses it, and a
document that carries it would simply age from the later of it and `created`.

## Consequences

- The queue is monotonic in the absence of `--verified`: writing into a document can no longer
  remove it, which is what makes a re-check safe to record.
- A never-verified document reports stale one cadence after **creation** rather than after its
  last edit. On a corpus whose documents are edited more often than their cadence, this reports
  more documents than before — correctly; those are the documents nobody has confirmed.
- The clock start is `created`, which is not necessarily when the thing the document tracks
  began. For a document standing in for an external ask, `created` precedes the ask, so silence
  is under-reported by that gap, once, at the document's birth. Bounded by the gap and paid only
  once, against a defect that cleared the entry on every edit.
- issue-9ed4905e0db8's rule — a mechanical rewrite must not advance `updated` — no longer has
  staleness behind it, since `updated` no longer feeds the clock. It stands on its own ground:
  `updated` is the edit clock every read view shows, and a bulk rewrite claiming every document
  was edited today is a lie about that.
- **Two builds reading one store disagree about `stale`, silently.** Measured by the
  cross-version procedure adr-ab4598c6f707 requires: one document, `created: 2024-01-01`,
  `updated` today, never verified, 365-day cadence — 0.23.0 reports `stale: false` and this
  build reports `stale: true`, from the same file. Neither refuses, so it is not a break by
  that decision's own test; it is the third thing that decision does not name, a field both
  builds show with different values. `stale` is computed and carries no provenance, so nothing
  reports the disagreement, and `doctor`'s `stale-index-build` does not cover it — a teammate
  who runs `reindex` themselves clears that finding while still reading the old rule. It
  resolves when everyone upgrades, and until then the review queue is per-build. This did not
  appear on docir's own corpus, whose oldest document is younger than the shortest cadence in
  its schema.
