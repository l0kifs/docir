---
code:
- src/docir/modules/documents/domain/services/chunking.py
created: '2026-08-15'
description: merge-forward keeps the first heading, then the merged block hard-splits,
  so the second section's heading names no chunk and matched_section can never point
  at it.
id: issue-66d43f63e441
related:
- adr-927aa43d9635
status: open
tags:
- retrieval
- material
title: A short section before an over-long one erases the long one's heading from
  the index
type: issue
updated: '2026-08-15'
---

## What happens
`_merge_short` folds a section under `MIN_CHUNK_CHARS` into the one that follows
and keeps the **first** heading — deliberately, so the merged block is named by
the heading a reader would name. `_split_long` then hard-splits anything over
`MAX_CHUNK_CHARS`, and only the first piece keeps the heading.

Compose the two and a heading disappears. Reproduced on `arch-0a3c2d6d54a6`:

    149  Backbone
   1150  (continuation)     <- the whole "Event timeline" section

`Backbone` is 149 characters, so it merges forward into `Event timeline`. The
merged block is ~2,000 characters, so it splits — the first piece keeps
`Backbone`, and the table that is the entire `Event timeline` section becomes an
unaddressable continuation.

## Why it matters
`Event timeline` exists in the body and `docir get <id> --section "Event
timeline"` returns it, but no chunk carries that heading. So `matched_section`
can never name it, and the read path that exists to point an agent at the right
heading cannot point at this one. A semantic hit on the table reports
`Backbone`, whose own text is six words and does not contain what matched.

It needs a short section immediately before an over-long one, so it is rare —
but nothing warns, and the symptom is a heading that is silently unreachable
rather than an error.

## Candidate fixes
Re-splitting the merged block on the original section boundary is the obvious
one: if a merged block has to be hard-split anyway, the merge bought nothing and
should be undone. Alternatively `_split_long` could re-attach the heading of any
section whose start falls inside a continuation piece.

Either way the guard has to assert the invariant directly — **every level-2+
heading in a body names at least one chunk** — over a body shaped like this one,
because a count of chunks cannot tell a swallowed heading from a merged one.
