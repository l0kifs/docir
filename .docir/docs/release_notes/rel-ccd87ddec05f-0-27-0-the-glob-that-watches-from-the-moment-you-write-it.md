---
created: '2026-09-17'
description: 'A code: glob now reports drift from the write that declared it rather
  than from a review almost nobody performed, and a store says which docir it needs
  before an older build fails on the wrong thing.'
id: rel-ccd87ddec05f
related:
- adr-49bb8cc48938
- adr-36d6156ffab9
- adr-6d4d43d44075
- adr-237b117a7916
- adr-6aa2e2f5f403
- adr-bc45b0bb1023
- issue-6e4ccac453ed
- issue-c30895cc62a3
- issue-2f07f83e6b84
- issue-1e310cf366b8
- issue-8b227c299e63
- issue-68df009b4e43
status: published
tags: []
title: 0.27.0 — the glob that watches from the moment you write it
type: release_note
updated: '2026-09-17'
---

## 🎯 The thesis

A `code:` glob used to be a promise nothing kept. It named the code a document governs, and
`docir check` said nothing when that code moved — because the drift digest was written by
`docir update --verified` and by nothing else. In docir's own store that was **all 99
documents** naming the code they govern, and the check could fire on none of them.

0.27.0 makes the glob watch from the write that declares it, and makes a store say which docir
it needs before a build that cannot read it fails on the wrong thing.

## 🎯 New Features

- **A `code:` glob is watched from the write that declares it.** `docir check` reports
  `code-drifted` when the files behind a pattern stop being the ones the document was pointed
  at — no review step to reach first. `docir update <id> --verified` upgrades the same watch to
  `code-changed`, the stronger claim that somebody *read* the two against each other. Both are
  warnings: code landing ahead of its prose is ordinary, not damage.
- **A store records the docir it needs.** `store_format:` is read before the schema resolves, so
  an older build stops with the version it needs instead of a parse error about a key nobody
  removed. `docir check --fix` writes the line and keeps the file's comments.
- **`docir doctor | jq '.compat'`** carries the store-format numbers to compare against another
  machine's docir, and every surface this build will stop accepting with the date it stops — so
  "is this urgent" is answerable without asking. Over MCP, ask `docir_deprecations`.

## 🐛 Bug Fixes

- **A `**` glob no longer fingerprints the package's bytecode.** 19 of the 39 files one glob
  matched here were `.pyc`, so a digest moved when no line was edited and differed by
  interpreter version.
- **A store that will not open no longer takes the MCP server down.** The tools still list and
  every call returns the reason, instead of the client seeing a closed connection.
- **A daemon that dies at startup says why.** The readiness timeout quotes what the daemon wrote
  rather than reporting the wait as if it were the diagnosis.

## ⬆️ Upgrade notes

Run **`docir check --fix`** once. It files a baseline for every `code:` glob that has none, so
drift is watched from that run onward, and records `store_format:` if your schema needs it. Both
report one action per document.

Expect `docir check` to report `code-drifted` on documents that were silent before. That is the
feature: a glob nobody had verified was watching nothing. They clear by reading the document
against the code and stamping `--verified` — nothing mechanical can, by design.

If a teammate stays on 0.26.0, their first command refuses the migrated index (they delete
`index.db*` and reindex, once), and their writes drop keys their build does not know. Run `docir
check --fix` after; it refiles what was dropped.

## 🔗 Full Changelog

See [CHANGELOG.md](https://github.com/l0kifs/docir/blob/v0.27.0/CHANGELOG.md)
