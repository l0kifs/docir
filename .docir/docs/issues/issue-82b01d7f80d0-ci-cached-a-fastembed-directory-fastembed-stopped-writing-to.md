---
code:
- .github/workflows/ci.yml
created: '2026-08-25'
description: 'The model cache never hit: the workflow cached ~/.cache/fastembed while
  fastembed 0.8 writes to $TMPDIR/fastembed_cache, so every run re-downloaded 64MB.'
id: issue-82b01d7f80d0
owner: maintainer
related:
- issue-87410666c867
- adr-ab9c454b760c
status: resolved
tags:
- cli
- embeddings
- testing
title: CI cached a fastembed directory fastembed stopped writing to
type: issue
updated: '2026-08-25'
---

## What was wrong

The workflow cached `~/.cache/fastembed`. fastembed 0.8 resolves its cache to
`tempfile.gettempdir()/fastembed_cache` — `/tmp/fastembed_cache` on a Linux
runner — so the key never hit, the post-step had nothing to save, and every run
re-downloaded the ~64 MB model while the step's own comment claimed it was
downloading them once.

Run 32880647217 says it plainly: `Cache not found for input keys:
fastembed-Linux-bge-small-en-v1.5`, and `Post Cache the embedding model` took 0s.
It had never hit.

`~/.cache/fastembed` is not an invented path — it is where an older fastembed
wrote, and a stale 64 MB copy of the default model still sits there on this
machine while the live cache at `$TMPDIR/fastembed_cache` holds 305 MB. So the
workflow was right when it was written and went quietly wrong under an upgrade,
which is the same shape as the drift docir's own `schema-drift` finding exists
to report.

## The fix

A job-level `FASTEMBED_CACHE_PATH` pins where fastembed writes, and the cache
step names the same expression. Both sides read `${{ runner.temp }}/fastembed-cache`,
so they cannot disagree again.

An expression rather than `~/.cache/fastembed`, and that detail is the whole
bug: a job-level `env:` value is **not** shell-expanded, so a literal `~` would
have fastembed create a directory actually named `~`. `actions/cache` *does*
expand `~` in its `path:`. One side expanding and the other not is how the two
came to name different directories in the first place.

Measured locally against a cold directory: 5 files fetched, 64 MB, ~8s; the
second run with the same variable set costs 0.93s and fetches nothing.

## How it was found

Reading the step timings of the first run of the new `reindex` -> `doctor
--strict` -> `check --strict` sequence (issue-87410666c867), because the reindex
took 100s rather than the ~70s measured locally. Nothing was failing, and nothing
would have started failing — a cache miss only costs time, which is exactly why
it survived.
