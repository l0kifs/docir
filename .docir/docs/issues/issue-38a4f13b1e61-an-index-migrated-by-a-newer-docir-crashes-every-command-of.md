---
created: '2026-09-05'
description: An older build finds a migration revision it does not ship and dies in
  alembic before any docir code runs, so the finding that exists to report exactly
  this is never reached.
id: issue-38a4f13b1e61
owner: maintainer
related:
- arch-0a3c2d6d54a6
- issue-d891ab5501e6
status: open
tags:
- integrity
- persistence
title: An index migrated by a newer docir crashes every command of an older one
type: issue
updated: '2026-09-05'
---

An index migrated by a newer docir kills every command of an older one. The older build's
alembic knows nothing about the revision it finds recorded, so `run_migrations` raises before
any docir code runs — including the code that exists to diagnose exactly this.

## What was observed

Two builds sharing one `DOCIR_HOME`. The newer one (main, carrying migration `0009`) opens the
store; the older one (0.23.0, the newest release, whose head is `0008`) then runs:

    alembic.script.revision.ResolutionError: No such revision or branch '0009'
    alembic.util.exc.CommandError: Can't locate revision identified by '0009'

A raw traceback on stderr, not a `DocirError`. It names neither store, nor the two versions,
nor what to do. `get`, `query`, `check`, `reindex` and `doctor --strict` all die the same way:
every command that opens the index, which is every command that is not `--help`.

`reindex` and `doctor` failing is the sharp end. They are the two documented recovery paths —
`doctor` is specified to snapshot the environment *before* it dispatches and to create a
missing index — and both are unreachable in the one state that needs them.

## Why the existing diagnostic does not fire

`MaintenanceService.stale_index_build()` already covers this direction. It compares by
inequality rather than "older than", precisely so a downgrade is reported too, and
`docir doctor` renders it as `stale-index-build` with the version that built the index.

It never gets the chance. The composition root calls `run_migrations` when it opens the store
(`platform/persistence/engine.py`, `entry_points/composition.py`), so alembic resolves the
recorded revision against this build's script directory before any service is constructed. The
finding is correct, reachable only from a session that already succeeded in opening the index,
and therefore never emitted for an index this build cannot open.

## Blast radius

The index is gitignored, so a clone is unaffected and a teammate on an older docir who never
ran the newer one sees nothing. What is affected is one working copy touched by two builds:

- the cross-version check adr-ab4598c6f707 mandates before shipping, which points a released
  build at a store the working build created — this is how it was found;
- a rollback after an upgrade, in either order;
- a project-local `uv` docir alongside a global install.

## Recovery

Delete the derived index and let the older build rebuild it — the index is a compile artifact
and nothing lives only in it:

    rm .docir/index.db*
    docir reindex

Verified: the older build reindexes and reads the store cleanly afterwards.

## Not a regression

Migration `0009` (`isolated:`) shipped unreleased in 0813112. Every release before it has the
same shape against any store a newer build has opened; `0009` is only the first revision to sit
past a published head while a published build is still installed.
