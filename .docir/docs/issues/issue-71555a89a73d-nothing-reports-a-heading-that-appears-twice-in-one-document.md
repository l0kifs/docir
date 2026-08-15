---
code:
- src/docir/modules/documents/domain/services/similarity_lint.py
created: '2026-08-15'
description: A repeated heading makes --section resolve to the first occurrence and
  leaves the second unreachable by name, silently.
id: issue-71555a89a73d
related:
- adr-927aa43d9635
status: open
tags:
- retrieval
- cosmetic
title: Nothing reports a heading that appears twice in one document
type: issue
updated: '2026-08-15'
---

## What happens
`_locate_section` returns the first heading whose text matches, so a document
that uses one heading twice has a second section nothing can address. Found by
hand in `ref-1509d5dbb4c3`, a probe log that reused
`## Findings produced BY these changes` for two sessions: `--section` returned
3,731 characters and the other 4,003 were reachable only by fetching the whole
body.

The document was fixed by dating both headings. Nothing would have reported it.

## Why it is only a warning
First-match is the right resolution rule — an error would refuse to read a
document that is merely repetitive, and hand-editing markdown is permitted, so
the corpus can acquire one at any time. The gap is that the condition is
invisible, not that the behaviour is wrong.

One occurrence in 142 documents, so this is a slow leak rather than a live
problem, and it is exactly the shape Tier 2 exists for.

## What it needs
An `ambiguous-heading` advisory beside `oversized-section` in
`docir lint --deep`, naming the document and the heading. Cheap: the heading
list is already computed by `scan_headings`, and the check is a count.

The guard has to assert *which* heading it found, not merely that it found one —
a count cannot distinguish a corpus with no duplicates from a scan that looked
at nothing.
