---
created: '2026-10-16'
description: 'docir update stops reporting success on body edits it did not make:
  an append to an existing heading lands under it, and a body with no edit mode is
  refused instead of dropped.'
id: rel-ddd587a7dcda
related:
- issue-a5515fc8bdc3
- issue-f47b4c69367b
- arch-0368cc754c15
status: published
tags: []
title: 0.30.1 — a body edit lands where you named it, or is refused
type: release_note
updated: '2026-10-16'
---

## 🎯 The release

**A body edit lands where you named it, or is refused — it is never dropped.**

Two `docir update` calls reported success on an edit they had not made. Both exited 0 and
printed a document, so an agent had no way to tell from the reply that its text was lost or
misplaced; only reading the body back showed it.

## 🐛 Bug fixes

- **`--append-section` on a heading the body already has adds under it** (GitHub #37). It
  wrote a second `## Context` at the end on every call, and since every section operation
  resolves a heading to its first occurrence, the appended text was out of reach of
  `--section` and `--replace-section`. Now the existing heading is extended and never written
  again:

  ```bash
  docir update adr-0001 --append-section "Context" --body "One more constraint."
  ```

  Prose lands at the end of the heading's own text, before any sub-heading of its; text
  opening with a sub-heading becomes its last sub-section. Text carrying a heading at the
  section's level or above is refused — append that heading as its own section. A heading the
  body lacks still becomes a new section at the end, as before.

- **`docir update` refuses a body no edit mode would write** (GitHub #36). `--body`,
  `--body-file` or `--stdin` without `--append-section`, `--replace-section` or
  `--replace-body` printed the unchanged document and exited 0; over MCP, `body` beside
  `replace_body` was discarded the same way. All of these now exit 2 naming the modes, and
  nothing in the call is applied — a metadata flag beside the stray body does not half-land.

## ⬆️ Upgrading

- Run `docir agent update` so the installed skill describes both behaviours.
- A script that passed a body on every `update`, mode or not, now fails where it was losing
  the text. Blank text is still accepted.
- A document the old append already doubled is listed by `docir lint --deep` as
  `ambiguous-heading`. Merge the two copies from `docir get adr-0001` and write the result
  back with `docir update adr-0001 --replace-body --force --stdin`: `--remove-section` deletes
  the *first* copy, which is the one holding the original text.

## 🔗 Full changelog

See [CHANGELOG.md](https://github.com/l0kifs/docir/blob/v0.30.1/CHANGELOG.md)
