---
created: '2026-09-04'
description: Staleness fell back to `updated` when `verified` was absent, so writing
  a re-check into a document nobody had vouched for cleared it from the review queue.
id: issue-6726eabcf871
owner: maintainer
related:
- adr-bd7c4f3c5764
- issue-9ed4905e0db8
- arch-0a3c2d6d54a6
status: resolved
tags:
- integrity
- schema
title: A document leaves the staleness queue when anyone edits it
type: issue
updated: '2026-09-05'
---

`docir check` reports `stale` for a document past its type's `review_days` cadence, and the
clock ran from `verified` **or, when that was absent, `updated`**. Every edit moves `updated`.

So a document nobody has vouched for left the review queue because somebody wrote in it.

## What was observed

Observed twice independently on 2026-08-31, on documents one day past a 14-day cadence.

`docir check` reported six overdue documents. Two were re-checked: both were open asks made of
another team, both still unanswered, so neither was stamped `--verified` — stamping would assert
somebody had answered. The re-check was written into each body instead.

Both then read `verified: None`, `updated: 2026-08-31`, `stale: false`, and `docir query --stale`
returned nothing. Nothing had been answered. The queue emptied because it was read.

## Why the `updated` fallback cannot work

The queue asks "who has confirmed this is still true?" and `updated` answers "when was this file
last touched?". Those come apart hardest in the document that matters most: the evidence that an
ask is still unanswered is a re-check written into the body, so recording the silence is what
ends the report of it. The longer a document goes unanswered, the more re-checks it accumulates,
and the more reliably it disappears.

This is issue-9ed4905e0db8 one level out. That issue stopped `tag rename` from advancing
`updated`, because a bulk administrative edit would forge the review clock. The forgery is not
specific to mechanical edits: any edit forges it, because the clock was reading the wrong field.
The fallback is the room; `tag rename` was one door.

The scope is every type with a cadence, not one workflow. An edit to a stale `decision`,
`architecture`, `reference` or `runbook` cleared it the same way.

## Reproduction

A store whose `issue` type declares `review_days: 14`. One document, `created`/`updated`
2026-08-16, no `verified`. On 2026-09-05:

    docir check                  # 'issue-…' is 5 day(s) past its 14-day review cadence
    docir query --stale          # [ the document ]

    docir update issue-… --append-section "Re-checks" --body "escalated, still no answer"

    docir query --stale          # []
    docir check                  # no `stale` finding

## Measured

On this store (2026-09-05, 196 live documents, 84 carrying a cadence, 1 carrying `verified`):
ageing from `created` instead of `updated` reports the same 0 stale documents — the corpus is
younger than its shortest cadence — while ageing from `verified` alone, treating absent as
infinitely stale, reports 83 of 84. That last is the shape issue-40d1792bc9f9 rejects: a warning
that fires on the product's own defaults.
