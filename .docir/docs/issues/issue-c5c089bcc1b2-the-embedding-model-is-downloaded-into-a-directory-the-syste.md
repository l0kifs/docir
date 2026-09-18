---
code:
- src/docir/platform/embedding/fastembed.py
- src/docir/config/settings.py
code_baseline:
  src/docir/config/settings.py: d20a58cb3775
  src/docir/platform/embedding/fastembed.py: e9b26d3e330b
created: '2026-09-18'
description: fastembed's default cache is under the temp directory, so the 64 MB download
  is re-paid whenever the OS sweeps — and where there is no temp directory, every
  read crashes before docir runs.
id: issue-c5c089bcc1b2
owner: maintainer
related:
- issue-b9800d8265f6
- adr-ab9c454b760c
status: resolved
tags:
- cli
- retrieval
title: The embedding model is downloaded into a directory the system may delete
type: issue
updated: '2026-09-18'
verified: '2026-09-18'
verified_code:
  src/docir/config/settings.py: d20a58cb3775
  src/docir/platform/embedding/fastembed.py: e9b26d3e330b
verified_content: e7c32bdcb31b
---

## What is wrong

docir left fastembed to pick where the embedding model is kept, and its default is
`tempfile.gettempdir()/fastembed_cache`. A downloaded model is durable state — 64 MB
on this machine — and a temp directory is where the system puts state it is entitled
to delete. So the download is re-paid whenever the OS sweeps, silently, as a read
that takes 16 seconds instead of two.

The same default is why a sandbox with no usable temporary directory cannot read at
all. `define_cache_dir` computes that path **before** it reads `FASTEMBED_CACHE_PATH`:

```python
default_cache_dir = os.path.join(tempfile.gettempdir(), "fastembed_cache")
cache_path = Path(os.getenv("FASTEMBED_CACHE_PATH", default_cache_dir))
```

so `gettempdir()` raises before the override is consulted, and setting the variable
does not help. Only passing `cache_dir` does.

## Measured

Left open by [[issue-b9800d8265f6]], which closed docir's half of the same sandbox.
With `tempfile.gettempdir()` made to raise, against this repository's own corpus:

| command | before | after |
|---|---|---|
| `docir query` | crashed in fastembed | answers |
| `docir get` | crashed in fastembed | answers |
| `docir search` | crashed in fastembed | answers |
| `docir context` | crashed in fastembed | answers |
| `docir check`, `doctor`, `daemon status` | answered | answers |

The reported environment was milder — writes to `TMPDIR` were denied but a read
answered — so the everyday half is the sweep, not the sandbox.

## What would fix it

Pass `cache_dir` explicitly, pointing at a **user-level** directory. Not the resolved
store: a project store is one per repository and a committed artifact, so a copy
inside each would be downloaded per repository and would need gitignoring to stay out
of every teammate's working tree. The model is identical for every store on the
machine.

`FASTEMBED_CACHE_PATH` has to keep working where somebody set it. This repository's
own CI pins it and caches that directory, and two sides naming different directories
is the defect its workflow comment already records.

The reasoning is [[adr-78090be868ec]].

## Resolution

FIXED 2026-09-18. `model_cache_home()` answers `~/.docir/models`, honouring
`FASTEMBED_CACHE_PATH`, and the composition root passes it to the adapter as fastembed's
`cache_dir`. The reasoning, the alternatives refused and the one-time cost are
[[adr-78090be868ec]].

Against this repository's own 233-document corpus with `tempfile.gettempdir()` made to
raise, every read now answers — `query`, `get`, `search` and `context`, the last of which
loads the model. Before, all four crashed inside `define_cache_dir`. The two commands
[[issue-b9800d8265f6]] fixed already worked, so the class is closed rather than narrowed.

Nothing re-embedded: `model_id` identifies the model and not its location, so
`embeddings_pending` stayed 0 and the released 0.27.0 reads the same store and ranks the
same first hit.

`models/` is in the generated store `.gitignore` too. It only matters where the store *is*
the global `~/.docir` — somebody keeping personal notes there under git would otherwise
commit 64 MB — and it arrived through the refresh [[issue-712f5bd17908]] built, which is
the first entry that machinery has carried in anger. Doing so exposed one flaw in it and
closed that as well: a second entry added by the same version repeated the "Added by
docir" header, which is noise in a committed file and happens whenever a store is upgraded
again before the next release.

`docir doctor` reports the path under `embedding.cache`, because "why did that command take
sixteen seconds" and "where did the disk go" are the same question and nothing answered
either.

Six injections, each proven to fail its guard: deriving the path from the temp directory
again, ignoring an explicit `FASTEMBED_CACHE_PATH`, treating an empty one as a choice, the
adapter dropping the path, the composition root not wiring it, and the header repeating
per run.
