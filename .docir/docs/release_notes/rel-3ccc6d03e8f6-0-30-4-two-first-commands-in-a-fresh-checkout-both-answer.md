---
created: '2026-10-21'
description: 'Commands racing to open an unbuilt index no longer fail: the first build
  happens once under the write lock, and the others wait for it and read what it built.'
id: rel-3ccc6d03e8f6
related:
- issue-308e5207c77b
- adr-e53c813d2f13
status: published
tags: []
title: 0.30.4 — two first commands in a fresh checkout both answer
type: release_note
updated: '2026-10-21'
---

## 🎯 The release

**Two first commands in a fresh checkout both answer.**

A fresh clone or `git worktree` has no index yet, so the first command builds one. When two
commands started at once — the ordinary case for an agent that issues its first two reads in
parallel — both found the index empty and both built it, and the slower one exited 1 with a raw
traceback: `UNIQUE constraint failed: tags.key`, or `table alembic_version already exists` when
they started within a fraction of a second. Over the daemon both clients answered, but a second
daemon died at startup with the same error, which only `daemon.log` showed.

## 🐛 Bug fixes

- **The first build of an index happens once, however many commands race for it**
  (issue-308e5207c77b, GitHub #42). Creating the index tables and the first build now take the
  database's write lock before they look, so a second command waits for the first and then finds
  the index built. Opening an index that is already built takes no lock, so ordinary commands do
  not queue behind a writer.
- **Large stores no longer give up while another command builds.** The wait for that build is
  up to five minutes rather than five seconds: on a 2,000-document store the first build takes
  ~20s, and four simultaneous first commands now all succeed where 0.30.3 failed three.

## ⬆️ Upgrading

- Nothing in a store changes and nothing needs rebuilding. Upgrade with `docir self upgrade`.
- The fix lives in the build that opens the store, so a machine still on an older release can
  still lose the race. If one does, run the failed command again: the command that won built a
  complete index, and `docir doctor` confirms it.

## 🔗 Full changelog

See [CHANGELOG.md](https://github.com/l0kifs/docir/blob/v0.30.4/CHANGELOG.md)
