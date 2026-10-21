---
code:
- src/docir/platform/persistence/engine.py
- src/docir/modules/documents/application/services/index_rebuilder.py
code_baseline:
  src/docir/modules/documents/application/services/index_rebuilder.py: 8071516073c0
  src/docir/platform/persistence/engine.py: 627f3000768c
created: '2026-10-21'
description: The migration and the store bootstrap each read before taking SQLite's
  write lock, so a second process opening an unbuilt index created or inserted what
  the first had just committed.
id: issue-308e5207c77b
owner: maintainer
related:
- adr-e53c813d2f13
status: resolved
tags:
- persistence
- integrity
- cli
title: Two first commands in a fresh worktree race to build the index, and the loser
  fails
type: issue
updated: '2026-10-21'
---

## What is wrong

Two first commands in a fresh clone or `git worktree` both open an index nobody has built,
and the slower one exits 1 with a raw SQLAlchemy traceback. pysqlite starts a transaction at
the first *write*, so each process reads before it holds the write lock, and each acts on
what it read. Two check-then-act steps race this way on the path that opens a store:

- the migration: both read "no version table" and both create the tables, and the loser
  fails with `table alembic_version already exists` or `table documents already exists`;
- the bootstrap ([[adr-e53c813d2f13]]): both count zero documents, the loser's rebuild
  reads an empty tag table, waits for the lock, then inserts what the winner just committed:
  `UNIQUE constraint failed: tags.key`.

The decision record said the second rebuild was idempotent. It was not, and nothing tested it.

## How it showed

Reported as GitHub #42 against 0.30.3, and reproduced on the unchanged source with the
report's script: 500 generated documents, two `docir --no-daemon get` in each fresh worktree.
At start gaps of 0.3–0.5s the second command failed on the tag insert every time; at
0.1–0.2s the *first* one failed in the migration. Over the daemon both clients answered, but
the second daemon died at startup with the same error, visible only in `daemon.log`.

Large stores failed regardless: four simultaneous first commands on 2,000 documents left
three failed, because the waiters gave up after the five-second busy timeout while the
winner's rebuild took ~20s.

## Resolution

Both steps now take SQLite's write lock before they look (`BEGIN IMMEDIATE`), and only an
answer given under the lock decides:

- an index already at the current schema migrates without taking any lock, which is every
  open but the first; anything else upgrades inside one transaction holding it;
- the bootstrap counts once unlocked, and if the index looks empty, counts again under the
  lock and returns without rebuilding when another process got there first;
- `docir reindex` and `check --fix` read under the same lock, since a rebuild writes the
  difference between what it read and the files.

The lock waits up to five minutes rather than the usual five seconds: what holds it is a
rebuild, and the waiter needs exactly what that rebuild produces. Waiters do not slow the
rebuild; four-way races finished in 27–38s against 26–35s alone, at 2,000 documents.

## Verification

Pinned by two openers racing on real connections, a deterministic replay of the winner
committing between the loser's look and its lock, and tests that the migration holds the
lock, that an index at head takes none, and that `reindex` reads under it. Eight bugs were
re-injected, one per guard, and each was caught. The report's script now passes at every
gap from 0 to 0.8s, as do six simultaneous commands at 500 documents and four at 2,000.
