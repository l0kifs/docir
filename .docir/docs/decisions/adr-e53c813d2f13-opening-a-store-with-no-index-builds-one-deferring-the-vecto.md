---
code:
- src/docir/entry_points/composition.py
created: '2026-08-29'
description: Why a fresh clone or git worktree now rebuilds its index on open instead
  of failing until someone runs reindex, why only the empty case qualifies, and why
  the embedding drain stays off that path.
id: adr-e53c813d2f13
owner: maintainer
related:
- issue-e5a0cb196607
- adr-909734bced92
- adr-6a4718fa7a7d
- arch-90c90751344f
status: accepted
tags:
- cli
- integrity
- embeddings
- architecture
title: Opening a store with no index builds one, deferring the vectors
type: decision
updated: '2026-08-29'
---

## Context

`.docir/docs/` is committed and `index.db` is gitignored, so a store arrives on a machine
with its files and no projection of them. That is not an edge case: it is every fresh clone,
every new `git worktree`, every CI checkout, and every machine a person adds.

In that state every read answered nothing and every write reported the document missing
(issue-e5a0cb196607). Nothing repaired it. The daemon's watcher rebuilds what *changes*, and
an untouched checkout changes nothing, so the store stayed unusable until somebody remembered
`docir reindex` — a step no error named until this release, and one docir's actual user, an
agent, has to be told about twice: once to learn it exists, once to run it and retry.

The reason it was a manual step was a cost estimate, and the estimate was wrong. `docir
reindex` on this repository's 191 documents takes ~70s, which is indeed too much to charge a
`get`. But ~69s of that is the embedding drain: it loads the ONNX model and writes 1,454
vectors. The rebuild itself — files to rows, FTS, the relation and mention graphs, the id
counters, both stamps — is **~0.9s** against a 0.98s baseline `get`.

## Decision

Opening a store whose index is empty while `docs/` holds files rebuilds it, in
`build_container`, before anything is dispatched. The vectors are deferred: every rebuilt
document is left dirty for the queue a write already uses, so no model is loaded on that path.

`MaintenanceService.bootstrap()` is `reindex()` minus the drain, sharing its transaction, so
the two cannot disagree about what a rebuild writes — both stamps included, or `check` would
report drift against an index docir had just built.

## Only the empty case

The predicate is `index_is_empty`, the same comparison behind `check`'s and `doctor`'s
`empty-index`. A store that is merely *behind* — one unparseable file, a hand-edit not yet
reindexed — is left alone and stays `index-behind-files`. Rebuilding on any disagreement would
make opening a store a corpus-sized write on every checkout carrying one broken file, and
would silently repair the condition `doctor` exists to report.

## The vectors are deferred, not skipped

Until the queue drains, `context` ranks on full text and the graph alone, and `docir doctor`
says so as `embeddings-pending`. That is a worse answer than a warm store and an answer, where
the state it replaces returned nothing at all.

A process with a background scheduler is woken — `EmbeddingScheduler.wake()`, abstract so each
implementation states its answer — and drains within the debounce window. A process without
one (`--no-daemon`, CI) leaves the queue standing until `docir reindex` or `docir embed
--flush`, which is why neither leaves the documented CI order.

This is not the recompute-only mode adr-6a4718fa7a7d rejected. That one skipped the rebuild
and recomputed vectors, writing neither stamp. This does the whole rebuild and defers only the
vectors.

## Peers are not bootstrapped

`build_peer_reader` opens a declared peer read-only and does not come through here. A
federated read that rebuilt another repository's index would make a read a write in a
repository nobody asked us to touch — the rule adr-fb938175f72a already sets.

## Consequences

- A fresh clone or worktree works without a command. The `no document with id` message that
  names an unbuilt index stays: it is now the backstop for the cases the bootstrap cannot
  reach — an index emptied under a running process, a store opened by a build that predates
  this one.
- `check --strict` on a fresh clone now checks a real graph rather than reporting
  `empty-index`. That strengthens the merge gate issue-87410666c867 created rather than
  removing it; the finding stays, unreachable in the ordinary case and correct in the rest.
- Opening a store can now write. With `--no-daemon`, parallel processes queue on SQLite's
  write lock and the losers find a populated index and skip — bounded by one rebuild, not N.
- The in-process CLI says what it did, once, on a terminal. Over the daemon the rebuild
  happens at daemon start and is visible where every other environment fact is: `docir
  doctor`.
- The cost is a measurement on one corpus, not a constant. It scales with the corpus (~5ms a
  document here), and a store large enough for that to matter should be measured before this
  decision is assumed to still hold.
