---
created: '2026-08-29'
description: Opening a store with files and no index now rebuilds it with the vectors
  deferred, and the miss that used to report the document as gone names the unbuilt
  index instead.
id: rel-07ece27606cd
owner: maintainer
related:
- adr-e53c813d2f13
- issue-e5a0cb196607
- adr-909734bced92
- adr-6a4718fa7a7d
- adr-f14682e3f4d6
status: published
tags:
- cli
- integrity
- release
- embeddings
title: 0.22.0 — a store that builds itself, and a message that stops denying the document
type: release_note
updated: '2026-08-29'
---

A store arrived on a machine with its documents and no index — a fresh clone, a new
`git worktree`, every CI checkout — and every read answered nothing while every write said
the document did not exist. Both halves are fixed here: the message stops asserting a
deletion that never happened, and the state stops occurring, because opening a store is now
what builds it.

## Upgrade notes

- **A fresh clone or `git worktree` no longer needs `docir reindex` before it can be read or
  written.** Opening the store rebuilds an index it finds empty — about a second on a
  190-document corpus — and leaves the vectors to the background queue. The explicit
  `docir reindex` is still what computes those vectors, so it stays first in the CI order.
- **`docir doctor`'s `no-index` finding is now a warning, not an error.** A `docir doctor
  --strict` that failed on a fresh checkout will start passing: the run reporting the finding
  is one of the things that repairs it. `empty-index` keeps the error severity, for the
  stores that rebuild does not reach.
- **Nothing else changes without you asking.** A store with a built index reads exactly as it did.

## 🎯 Opening a store with no index builds one

`.docir/docs/` is committed and `index.db` is gitignored, so a store arrives with its files
and no projection of them. Nothing rebuilt it: the daemon's watcher rebuilds what *changes*,
and an untouched checkout changes nothing. It stayed unusable until somebody remembered
`docir reindex` — which docir's actual user, an agent, has to be told twice: once that the
command exists, once to run it and retry.

It was a manual step because of a cost estimate, and the estimate was wrong. `docir reindex`
on this repository's 191 documents takes ~70s, but ~69s of that is the embedding drain,
loading the ONNX model to write 1,454 vectors. The rebuild itself — files to rows, full text,
the relation and mention graphs, the id counters, both stamps — is **~0.9s** against a 0.98s
baseline `docir get`.

So the bootstrap does the rebuild and defers the vectors. Every document comes out dirty in
the queue a write already uses, the daemon's scheduler drains it in the background, and
`docir doctor` reports what is still queued as `embeddings-pending`. Until it drains,
`docir context` ranks on full text and the graph alone — a worse answer than a warm store,
and an answer, where the state it replaces returned nothing at all.

Only the empty case, decided by the same comparison behind `docir check`'s and `docir
doctor`'s `empty-index`. A store merely *behind* is untouched and stays `index-behind-files`,
or one unparseable file would make opening a store a corpus-sized write on every checkout.
Peers are never bootstrapped: a federated read that rebuilt another repository's index would
make a read a write in a repository nobody asked us to touch.

## 🐛 `no document with id` stops denying a document that is on disk

`no document with id '<id>'` was the answer to every failed lookup, including the one where
the document is sitting in `docs/` and the index that answers for it was never built. The
message stated something false about the corpus and sent everyone to the wrong place: a
human looks for a deletion that never happened, and an agent — which cannot glance at the
directory and see the file — concludes the document is gone. The reporter of the issue lost
a document amendment to exactly that.

`docir check` and `docir doctor` had named this condition since 0.20.0, and neither runs on
the path that hits it. The message now names it, through the same comparison, and points at
`docir reindex`. Same error, same exit code 4, same prefix — only where it sends you changes.
With the bootstrap above it is the backstop rather than the common case: an index emptied
under a running daemon, or a store opened by an older build.

## 🔗 Full Changelog

See [CHANGELOG.md](https://github.com/l0kifs/docir/blob/v0.22.0/CHANGELOG.md)
