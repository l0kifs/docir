---
code:
- src/docir/platform/embedding/fastembed.py
- src/docir/config/settings.py
code_baseline:
  src/docir/config/settings.py: cc0bc51748d7
  src/docir/platform/embedding/fastembed.py: a407cf88f7c8
created: '2026-09-23'
description: fastembed builds its ONNX session with no thread limit unless one is
  passed; DOCIR_EMBED_THREADS caps it, and the daemon respawns when it changes.
id: issue-e9ef984d5ec7
owner: maintainer
related:
- adr-78090be868ec
status: resolved
tags: []
title: The embedding model takes every core, so warming, reindexing and searching
  saturate the CPU
type: issue
updated: '2026-09-23'
---

## What is reported

docir saturates the CPU. The reporter asks for a way to run it with a chosen number of threads,
and names the cause as the vector-search functionality: warming the model, reindexing, and
searching.

## What is behind it

One thing, on three paths. `fastembed` builds its ONNX session with no thread limit unless one
is passed, so the model takes every core it can see — while the model warms, while `reindex`
embeds a corpus, and while each `context` or `search` query is embedded. Nothing else in docir
spawns workers.

`TextEmbedding(threads=N)` sets both `intra_op_num_threads` and `inter_op_num_threads`, so one
number covers all three paths.

## Resolution

FIXED — `DOCIR_EMBED_THREADS` caps it.

An **environment variable and deliberately not a schema key**: a store is a committed artifact
read by whoever clones it, so a core count inside it would impose one machine's hardware on the
whole team. That is [[adr-78090be868ec]]'s argument for keeping the model out of the store, one
field over.

Unset changes nothing, so no machine gets slower by upgrading. An unusable value (zero,
negative, not a number) reads as unset rather than raising: this is read while every container
is built, `docir doctor` included, and a typo in a shell profile must not break the command
somebody runs to diagnose the problem.

`docir doctor` reports the cap under `embedding.threads`, absent when uncapped.

## The trap that had to be closed with it

The daemon resolves the cap once, when it builds its embedder, and answers every later request
from that. So setting the variable changed nothing until the daemon idled out — while `doctor`,
which reads the *client's* environment, reported the new value the whole time. A setting whose
own diagnostic lies about whether it is in force is worse than no setting.

The cap therefore joins the code stamp and the schema digest in the pid file, as a third
staleness input: a daemon spawned with a different cap is stopped and replaced, exactly as one
serving stale code is. An unusable value maps to `None` on both sides, so a typo does not
respawn the daemon once per command.

## Still open: the default

Unset remains fastembed's own behaviour — every core. That is the right default on a build
machine and the reported complaint on a laptop, and changing it would silently alter throughput
for everyone. Measured on this repository's 250-document corpus before deciding; the numbers
are on GitHub #23.
