---
code:
- src/docir/entry_points/daemon/lifecycle.py
- src/docir/entry_points/daemon/cmds.py
- src/docir/entry_points/doctor.py
code_baseline:
  src/docir/entry_points/daemon/cmds.py: f2ba24c1089c
  src/docir/entry_points/daemon/lifecycle.py: 0147e6d0a53d
  src/docir/entry_points/doctor.py: eeda831bac4b
created: '2026-09-18'
description: The daemon loads the schema once at startup, its watcher does not react
  to the schema file, and nothing stamps that file into the pid record — so a schema
  change is honoured only in-process until the daemon is stopped.
id: issue-c2e8ce341a00
owner: maintainer
related:
- adr-d2ae4604a01e
- arch-1cfb1b212237
status: resolved
tags:
- daemon
- schema
title: A docs-schema.yaml edit is invisible to every daemon-served command until the
  daemon is replaced
type: issue
updated: '2026-09-18'
---

## What is wrong

`build_container` resolves `docs-schema.yaml` once, and `_run_server` builds one
container for the daemon's whole life. Every request that daemon answers — Tier 0
validation included — reads the `Schema` object loaded at startup.

Nothing replaces it:

- The watcher's filter accepts `tags.yaml` and `*.md` and nothing else, so the
  schema file is not among the paths it reacts to. Its own module docstring names
  `docs-schema.yaml` as one of the hand-editable files whose stale-read window it
  closes, which is true of bodies and the tag registry and not of the schema.
- Even if it were watched, the only action is `reindex --changed`. A reindex makes
  the index agree with the files; it does not re-resolve the schema.
- The pid file's `CodeStamp` is the version plus the newest mtime across the
  *package* sources, so no file in the store can invalidate a daemon the way a
  changed build does.

## How it showed

Declaring a store check (`code-unverified`) in this repository's own schema:

```
docir check                # code-changed 17, code-drifted 46
docir --no-daemon check    # the same, plus code-unverified 95
```

Same store, same command, two answers. After `docir daemon stop` the two agreed.
The daemon idles out after 900s, so the window closes on its own only while
nobody is using the store, and never while somebody is.

## What else it reaches

Everything the schema decides, because it is one object serving every request:
a status, a relation kind, a `required:` field, `allowed_relations`,
`disable_types:`, the embed model, and the store's own `checks:`.

A relation kind added to the file is refused as unknown until the daemon is
replaced, and one removed from it keeps being accepted. That is a **write**
validated against a rule the file no longer states, which is a worse failure than
the stale read the watcher exists to prevent — and it is silent in both
directions.

The packaged skill tells an adopter to run `docir check` straight after editing
the schema. That is the command that answers from the stale copy.

## What would fix it

Two shapes, and the second reuses what already exists.

Watch the schema path and rebuild the container on a change — correct, but it
makes the watcher a second thing that constructs the object graph, and a rebuild
mid-request is a lifetime question the executor does not currently have.

Or fold the schema file's digest into the pid file's `CodeStamp`. A daemon whose
stamp does not match is already stopped and replaced by the next client, so the
schema would ride the mechanism that makes the daemon disposable, and the fix
would be a stamp input rather than a new lifecycle.

Verify by injection: with a daemon running, add a relation kind to
`docs-schema.yaml` and assert that a write using it succeeds with no manual
restart. Assert the accepted kind, not just an exit code — refusing the write and
refusing to start are the same failure to a test that only reads the status.

## Resolution

FIXED 2026-09-18, by the second shape: the schema rides in the pid file, so a
daemon that loaded a different one is stopped and replaced by the mechanism that
already makes a mismatched build disposable. No new lifecycle, and the watcher is
untouched.

`write_pid` takes the digest from its caller, and `_run_server` reads it *before*
`build_container` resolves the file. Reading it after would record a schema the
daemon may not be serving — this defect in miniature — while reading early can
only over-report a mismatch, which costs one respawn.

A pid file carrying no digest never matches, the same reading an unstamped build
gets and the same safe direction. `daemon status` and `docir doctor` report the
schema case apart from stale code: "stale code" sends a reader to `src/` for a
change that is in their own store.

Four guards, each proven by injecting the bug it claims to catch — reverting
`ensure_running` to code only, dropping the digest when the pid file is read,
making `status` stop reporting the mismatch, and silencing the doctor finding.
The first is a real subprocess: with a daemon running it adds a relation kind to
`docs-schema.yaml` and asserts the edge comes back carrying that kind, because a
refused write and a daemon that never came up are the same failure to a test that
only reads an exit code.

What is argued rather than pinned is the ordering inside `_run_server`. Recording
the digest after the load would leave a window no test opens, so the docstring
carries the reason instead.
