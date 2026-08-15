---
code:
- src/docir/modules/documents/domain/services/markdown_sections.py
- src/docir/modules/documents/domain/services/chunking.py
created: '2026-08-15'
description: markdown_sections.py has no fence tracking, so --section returns a fragment
  ending in an unclosed fence and --replace-section silently orphans the rest of the
  body.
id: issue-af046a467575
related:
- adr-927aa43d9635
status: resolved
tags:
- retrieval
- blocking
- integrity
title: 'Section reads and edits treat a fenced ## as a heading; the chunker does not'
type: issue
updated: '2026-08-15'
---

## What happens
`chunking.py` tracks fenced code blocks — a `##` inside a fence is prose, and
adr-927aa43d9635 says so explicitly. `markdown_sections.py` does not track them
at all: `_HEADING_RE` is matched line by line with no fence state. The two
therefore disagree about what the sections of a document *are*.

Reproduced on a body whose rule quotes a markdown template:

    headings the reader sees : ['Rule 7', 'Purpose', 'Owns', 'Rule 8']
    headings the chunker sees: ['Rule 7']

## Why it is blocking
Three failures, worst last.

`docir get <id> --section "Rule 7"` returns a fragment that stops at the fake
heading — ending with an **unclosed** fence. The reader gets invalid markdown
and no indication that anything was cut.

An unknown-heading error lists the phantom headings as real ones, so the flag
that exists to save a full-body read sends the caller to a heading that is not
a section.

And `docir update <id> --replace-section "Rule 7" --body "..."` writes the
replacement at the true start but ends it at the fake boundary, leaving the
remainder of the quoted template stranded at top level with a stray closing
fence. The body is corrupted, the command reports success, and nothing in
`docir check` detects it.

## Where it bites today
`arch-322e5f992ad2` (Architecture Rules) quotes a `CONTRACT.md` template in rule
7 and a decision-record template in rule 14. Both are inside fences, and both
currently read as sections — so that document cannot be edited section-wise
without losing text.

## What it needs
Fence tracking in `markdown_sections.py`, shared with `chunking.py` rather than
written twice — the two disagreeing is the defect, so a second copy of the rule
would only postpone it. `_locate_section`, `_section_end` and `section_headings`
all need it, since a caller can reach the same divergence through any of them.

The regression guard has to inject the bug: a body with a fenced `##`, asserting
that the reader and the chunker return the *same* heading list, and that a
replace round-trips without moving text outside the section.

## Resolution

Fixed by `markdown_headings.scan_headings`, one fence-aware scanner both
`markdown_sections` and `chunking` now read; the private regex pair is gone from
each. `arch-322e5f992ad2` reports 24 real sections where it used to report 25
with 10 phantoms, and `--section "7. Contract documentation"` now returns the
whole rule, fences balanced, at 1,051 characters.

`tests/modules/documents/test_markdown_headings.py` guards it two ways, and both
were verified by injecting the defect. Removing fence tracking from the scanner
fails 6 tests; giving the reader its own naive scanner again fails 5, including
the sweep over every document in this repo.

The agreement guard's first version asserted `chunked <= read`, which the second
injection passed — a naive reader returns *more* headings, which is the direction
the original bug went. It now asserts set equality against the shared scanner.
Worth remembering: the subset assertion looked like a check and was not one.
