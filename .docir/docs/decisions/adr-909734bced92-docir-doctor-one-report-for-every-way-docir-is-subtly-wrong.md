---
code:
- src/docir/entry_points/doctor.py
created: '2026-08-25'
description: Why the environment checks scattered across five commands became one
  command, and why the corpus is deliberately not part of it.
id: adr-909734bced92
owner: maintainer
related:
- kind: refines
  to: arch-1cfb1b212237
- adr-354a4270ecd8
- adr-31aa7aa60d11
- adr-fb938175f72a
- adr-ab9c454b760c
- ref-a3f4d3140e4e
status: accepted
tags:
- cli
- daemon
- embeddings
- integrity
title: docir doctor — one report for every way docir is subtly wrong
type: decision
updated: '2026-08-25'
---

## Context

docir has more ways to be subtly wrong than it has ways to fail. A daemon serves
reads from the code it loaded and keeps doing so after an upgrade; `DOCIR_EMBEDDER`
survives a test run and every read scores shared vocabulary instead of meaning; the
index is derived and gitignored, so a fresh clone has none and answers nothing; a
peer is skipped for schema skew; the schema moves in the package with nothing in
`git diff`. None of these raises. Each produces an answer that imitates a correct
one.

Every one was already detected somewhere — `daemon status`, `self status`, a stderr
line during a read, one finding among a hundred in `check`. What none of them was is
*reportable together*, which is the property that matters: you do not know which of
the six to look at, because if you did you would already know what was wrong.

## Decision

`docir doctor` reports the environment — the installation, this store's derived
index, the embedding model in force, the daemon, and each declared peer — as facts
plus findings, each finding carrying the command that closes it. It reuses the
existing checks rather than adding new ones.

Severity is derived from the finding's kind, the rule `CheckIssue` already follows.
`error` means docir cannot work correctly here; `warning` means it works less well
than the caller believes. `--strict` gates on errors only.

## The corpus is not its question

`docir check` owns the graph and answers it with a full scan. Doctor never walks it.
A diagnosis that costs what `check` costs is one nobody runs while something is
actually wrong, and `orphan` alone would bury every environment finding under the
default state of a healthy corpus.

The one corpus-shaped number it does carry is the pair `documents` /
`documents_on_disk`. That is not a corpus question but a wiring one: the index is a
projection of the files, so a difference *is* "your reads are answering from stale
state", and it is the only way a fresh clone stays visible once anything has created
an empty index.

## The environment is snapshotted before the first dispatch

Every command runs `ensure_running`, which stops a daemon serving other code and
replaces it, and every container build creates a missing index. So a doctor that
dispatched first would repair two of the conditions it exists to report and then
call them clean.

`snapshot()` therefore reads only this process, this environment and the filesystem,
and it runs first. The daemon finding is worded in the past tense for the same
reason: by the time it is printed, the stale daemon is gone.

## The store half is a dispatcher command

The index's account of itself is `store_status`, in the module that owns the index —
which keeps the version comparison and the drift diff implemented once, and makes
the half an agent can use reachable over MCP as `docir_store_status`
(adr-354a4270ecd8).

The split is not a convenience. The rest of doctor is unanswerable from the daemon:
which build *this* process loaded, what is in *this* shell's environment, which
store *this* working directory resolved to. A whole-command dispatcher tool would
have the daemon reporting on its own process, which makes "is the daemon stale?"
inexpressible.

## A broken store still produces a report

`execute` turns a domain error into a process exit. Doctor uses `try_execute`, which
returns the message instead, because "the store will not open" is the finding — and
exiting there prints nothing at the one moment somebody needs the environment half.

## Consequences

- Every finding kind classifies itself by being in `ERROR_KINDS` or not, so a new
  one cannot forget to.
- The model is loaded only under `--probe`, which is the one check that can change
  the machine: a cold cache downloads it. `probe_embedder` catches bare `Exception`
  — a truncated ONNX cache is not in docir's error taxonomy, and a traceback would
  make the diagnostic command the thing needing diagnosis.
- No network call, ever. The published-release answer is read from the cache the
  daemon leaves, so `latest` absent means *unknown* rather than up to date.
- The global `~/.docir` is excluded from `shadowed-store`: it sits above every store
  under the user's home directory, and being shadowed by a project store is what it
  is for. Reporting it would fire the finding on the ordinary correct setup, which
  is how a warning stops being read.
