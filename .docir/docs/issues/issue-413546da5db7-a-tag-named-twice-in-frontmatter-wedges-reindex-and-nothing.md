---
code:
- src/docir/modules/documents/domain/entities/document.py
- src/docir/platform/persistence/repositories.py
code_baseline:
  src/docir/modules/documents/domain/entities/document.py: 50d565fa6cdd
  src/docir/platform/persistence/repositories.py: 7bcf7e81a5a0
created: '2026-09-24'
description: Why a repeated tag failed every reindex, why a repeated glob or edge
  made --replace-body refuse the document for good, and where the repeat is now dropped.
id: issue-413546da5db7
owner: maintainer
related:
- arch-0368cc754c15
status: resolved
tags:
- integrity
- persistence
- cli
title: A frontmatter list naming one entry twice wedged reindex or refused --replace-body
type: issue
updated: '2026-09-24'
---

## Symptom

A frontmatter list that names one entry twice left the file and its index
disagreeing, and no command docir offers could bring them back together.

- **A tag** (`tags: [x, x]`). `docir add` or `update` wrote the file, then
  failed with a raw `sqlite3.IntegrityError: UNIQUE constraint failed:
  document_tags.doc_id, document_tags.tag_key`, exit 1. Every `docir reindex`
  after it failed the same way, so CI's `reindex -> doctor --strict -> check
  --strict` stopped at its first step. `docir doctor` reported
  `index-behind-files` and pointed at `docir check`, which named nothing — the
  file parses.
- **A code glob or an identical edge.** The index kept one and the file two, so
  the two hashed differently, and `update --replace-body` refused the document
  with exit 6, "changed on disk since it was indexed". Refetching re-read the
  same disagreement, so the refusal was permanent.

Measured on scratch stores, 2026-09-24.

## How a repeat reaches a file

The CLI drops a repeat before the write (issue-2bb30af6216d), so `--tags x,x` no
longer gets here. Everything else still can: the MCP `docir_add`/`docir_update`
tools take a list and pass it through, a hand edit or a merge of two branches
that each added the entry writes one, and so does a file left by an earlier
build.

## Resolution

`Document` drops a repeated tag, glob or identical edge when it is built,
keeping the first. Every path builds one — parsing a file, `add` and `update`
on either transport, `tag rename` — so the index, `content_hash` and every file
docir writes agree. A file that already holds a repeat reads without it,
reindexes, takes `--replace-body`, and loses the repeat on its next write.

The file is then the only place a repeat is still visible, so `docir check`
reads it there: `repeated-entry`, a warning naming the file and what it repeats,
and `docir check --fix` rewrites the file without it and leaves `updated` alone.
An edge is compared by what it says — `adr-1` and `{to: adr-1}` repeat — and two
kinds to one target are not a repeat: which one the author meant is a judgement.

A build that cannot read this fix still fails on a repeated tag. The packaged
troubleshooting reference says how to find the file and what to delete.
