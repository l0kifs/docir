---
created: '2026-09-05'
description: A verification could be stamped and never withdrawn, so correcting a
  bad stamp meant the hand-edit the CLI exists to prevent.
id: issue-b4813930bfca
owner: maintainer
related:
- adr-bd7c4f3c5764
- adr-d9e6d5ccd0b4
status: resolved
tags:
- integrity
- cli
title: No CLI clears a --verified stamp
type: issue
updated: '2026-09-05'
---

`docir update <id> --verified` stamps today. Nothing un-stamped it.

A stamp applied by mistake — during a sweep, or on a document that was re-read rather than
answered — was permanent short of hand-editing the file, which the CLI otherwise forbids and
`docir check` then reports as a hand-edit.

## What was observed

Reported against 0.23.0 on a corpus carrying two documents whose `verified:` line asserted a
review nobody had done. They were reported to their owners through a side script, because docir
itself had no way to take the claim back.

## Why it matters

Thesis 2 says the CLI is the only write path, and that is what guarantees frontmatter
consistency. A field the CLI can only set and never unset forces exactly the hand-edit the tool
exists to prevent — and then flags it. Every other optional field already has its clearing
spelling: `--set-owner ""`, `--set-code ""`, `--set-isolated ""`, `--set-tags ""`.

`verified` had none, because it is a flag rather than a value: `--verified` takes no argument, so
there was no empty string to pass.

## Resolution

`docir update <id> --clear-verified` erases the stamp (adr-f4e6ade4afd0). It records no
revocation date and grants no review window: the document ages from `created` again, exactly
where one nobody ever verified sits, so a stamp taken back on an overdue document puts it
straight back on the review queue.

That is the half worth stating, because the other withdrawal behaves differently on purpose. An
*edit* to a verified document also withdraws the verification, and that one does restart the
cadence — something true stopped being true. A stamp nobody earned was never true, and gets
nothing.

The flag is refused when no verification is standing, so it cannot manufacture review state on a
document nobody vouched for.
