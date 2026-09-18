---
code:
- src/docir/config/settings.py
- src/docir/platform/embedding/fastembed.py
- src/docir/entry_points/composition.py
code_baseline:
  src/docir/config/settings.py: d20a58cb3775
  src/docir/entry_points/composition.py: 88d0cea954b3
  src/docir/platform/embedding/fastembed.py: e9b26d3e330b
created: '2026-09-18'
description: Why the model is cached in the user-level ~/.docir/models, passed as
  fastembed's cache_dir argument rather than left to its temp-directory default.
id: adr-78090be868ec
owner: maintainer
related:
- kind: refines
  to: adr-ab9c454b760c
- issue-c5c089bcc1b2
status: proposed
tags:
- cli
- retrieval
title: Where a downloaded embedding model lives
type: decision
updated: '2026-09-18'
verified: '2026-09-18'
verified_code:
  src/docir/config/settings.py: d20a58cb3775
  src/docir/entry_points/composition.py: 88d0cea954b3
  src/docir/platform/embedding/fastembed.py: e9b26d3e330b
verified_content: b2b78259f95c
---

## Decision

The embedding model is downloaded to `~/.docir/models`, and docir passes that path to
fastembed as `cache_dir` rather than letting fastembed choose. `FASTEMBED_CACHE_PATH`
overrides it where somebody has set it.

## Why not the temp directory

That is fastembed's default, and it is wrong in one way said twice: a downloaded model
is durable state, and a temp directory is where the system puts state it may delete. The
consequence is a 64 MB download re-paid on every sweep, arriving as a read that takes 16
seconds instead of two, with nothing saying why.

Where there is no temp directory at all — a read-only agent sandbox — the default raises
before docir runs, and every read fails inside the library ([[issue-c5c089bcc1b2]]).

## Why not the store

A project store is one per repository and a **committed artifact**. A model inside it
would be downloaded once per repository, and would need a `.gitignore` entry to stay out
of every teammate's working tree — a 64 MB binary one `git add -A` away from the history.

The model is identical for every store on the machine, so it belongs to the machine.
`~/.docir` is the only docir directory that is already per-machine rather than
per-project, which is why it is not derived from `Settings.home`: the home a command
resolves is usually the project one.

## Why the argument and not the variable

Passing `cache_dir` is not a style preference. fastembed computes its default *before* it
reads the override:

```python
default_cache_dir = os.path.join(tempfile.gettempdir(), "fastembed_cache")
cache_path = Path(os.getenv("FASTEMBED_CACHE_PATH", default_cache_dir))
```

so in a sandbox `gettempdir()` raises and the variable is never consulted. Setting it
does nothing there; the argument is the only thing that works. Measured, not read off the
page.

## Why the variable still wins where it is set

docir reads `FASTEMBED_CACHE_PATH` itself and passes what it finds. A CI image that pins
it is naming a directory it also caches, and this repository's own workflow carries a
comment about the run where the two sides named different directories and the model was
re-downloaded every time while the step claimed otherwise. Overriding it would recreate
that.

## Cost

One re-download for every existing install, because the model moves. It is the last one
the sweep can force.

Nothing about the vectors changes: `model_id` identifies the model, not its location, so
no store re-embeds ([[adr-ab9c454b760c]]).
