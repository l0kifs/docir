---
code:
- src/docir/modules/documents/application/services/document_service.py
- src/docir/entry_points/cli/app.py
created: '2026-08-15'
description: docir update patches every other frontmatter field but not type, so retyping
  a corpus means hand-editing the markdown the CLI exists to own.
id: issue-4952ce77d19d
owner: maintainer
related: []
status: resolved
tags:
- cli
- blocking
- schema
title: A document's type cannot be changed after it is created
type: issue
updated: '2026-08-15'
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
