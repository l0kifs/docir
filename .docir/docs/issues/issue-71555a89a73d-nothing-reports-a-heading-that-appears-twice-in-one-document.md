---
code:
- src/docir/modules/documents/domain/services/similarity_lint.py
created: '2026-08-15'
description: A repeated heading makes --section resolve to the first occurrence and
  leaves the second unreachable by name, silently.
id: issue-71555a89a73d
related:
- adr-927aa43d9635
status: resolved
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

## Resolution

`SimilarityLinter.find_ambiguous_headings` reports it as a Tier 2 advisory,
naming the heading and how many times it appears. It reads `scan_headings`, so a
heading repeated inside a fenced block is not one.

Shipped alongside `unqualified-section-ref`, the paired gap found the same
afternoon: prose naming a section that lives in another document, which is what a
document split leaves behind.

That second check needed a correction before it was worth having. The first
version keyed on any heading in the corpus, and both findings it produced were
wrong: `Resolution` is a heading in dozens of issues, so quoting the word tripped
it, and where several documents share a name the "it lives in X" clause picked
one arbitrarily and named the wrong document. It now considers only headings
unique to a single document — a check that cannot say *which* document is not
entitled to the sentence. Both false positives are pinned as tests.

Verified by injection: removing the unique-owner gate fails
`test_a_heading_many_documents_share_is_never_flagged`.
