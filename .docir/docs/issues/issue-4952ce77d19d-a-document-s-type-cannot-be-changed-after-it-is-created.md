---
code:
- src/docir/entry_points/cli/app.py
- src/docir/modules/documents/application/services/document_service.py
code_baseline:
  src/docir/entry_points/cli/app.py: a15a6e7698f4
  src/docir/modules/documents/application/services/document_service.py: d9af2a92a8ba
created: '2026-08-15'
description: docir update patches every other frontmatter field but not type, so retyping
  a corpus means hand-editing the markdown the CLI exists to own.
id: issue-4952ce77d19d
owner: maintainer
related: []
status: resolved
tags:
- blocking
- cli
- schema
title: A document's type cannot be changed after it is created
type: issue
updated: '2026-09-18'
verified: '2026-09-18'
verified_code:
  src/docir/entry_points/cli/app.py: a15a6e7698f4
  src/docir/modules/documents/application/services/document_service.py: d9af2a92a8ba
verified_content: 010834c79d69
---

A document is written with a type and keeps it forever. `docir update` can
change the title, description, status, tags, edges, owner, governed globs and
body — everything the frontmatter carries except the one field that decides
which grammar all the others are checked against.

## Why it matters

Types are not a detail a corpus gets right on the first day. A store that
started on the bundled `software` profile and grew its own vocabulary has to
rename `decision` to whatever it actually calls one, and a corpus of any size
means hundreds of documents.

With no `--type`, the only route is editing the markdown by hand — the single
thing the write path exists to prevent. Hand editing writes a `type:` the
schema may not declare, in a file whose directory now disagrees with it, and
nothing validates either until the next `reindex`.

## What it is not

It is not a bulk operation. One document at a time through the CLI, driven by
`docir query --type <old>`, keeps every write validated; a bulk retype verb
would have to guess at the status mapping, which is the reasoning that killed
a bulk import.

## How it shipped

`docir update <id> --type <new>` retypes a document, and the id never changes — which is the
whole point, since every `related` edge in the corpus already names it.

Four properties make it safe to run across hundreds of documents:

- **The file moves, the filename does not.** The directory names the type, so leaving the file
  where it was would make the layout disagree with the frontmatter on every document a
  corpus-wide rename touches. `relocate` moves it and keeps the name.
- **A retype is not a status transition.** There is no edge between two types' status graphs to
  break, so nothing is reported as overridden. A status the target type does not declare is
  refused rather than silently reset.
- **Existing edges are re-validated**, because the target type may allow a narrower set.
- **It is not a content change**, so it does not move `updated` or revoke a verification.

Still one document at a time, driven by `docir query --type <old>`, exactly as *What it is not*
argued. [[run-781485012ad0]] is the procedure for the schema half — freeing the prefix the old
name holds.
