---
created: '2026-09-06'
description: 'The reply timeout stopped bounding how long a command may take, and
  vectors stopped being recomputed when nothing the model reads had changed: 146s
  to 2.6s on docir''s own corpus.'
id: rel-dd3ef6e7293a
owner: maintainer
related:
- adr-56d29d521620
- issue-77dd42e3a03a
- adr-31aa7aa60d11
- adr-6a4718fa7a7d
status: published
tags: []
title: 0.25.0 — an upgrade that finishes, and stops redoing work nobody asked for
type: release_note
updated: '2026-09-06'
---

`docir self upgrade` could not finish on a large corpus, and most of what took so long was work
it never needed to do. Two halves of one failure. The client bounded the daemon's reply at a
flat 300s, so the command that always makes docir's most expensive request was bounded by a
number chosen for an ordinary one. And that request re-embedded every vector in the store on
every release — including the releases that changed neither the model nor the chunking.

## Upgrade notes

- **The reply timeout no longer bounds how long a command may take.** The daemon sends a
  keepalive every few seconds while it works, and each frame re-arms the socket, so
  `DOCIR_REQUEST_TIMEOUT` now answers "has the daemon died?". There is no corpus size it has to
  be raised for; if you raised it, put it back.
- **Migration `0012` adds `embeddings.input_digest`** and upgrades an existing index in place.
  The first rebuild after upgrading recomputes every vector once, because a row written by an
  older build carries no record of what produced it. Every rebuild after that recomputes only
  what moved.
- **An index at schema `0012` is refused by docir 0.24.0 and earlier**, by name, with the
  rebuild that fixes it. The index is derived and gitignored, so a teammate on an older build
  deletes it and reindexes — `docir doctor` reports it as `index-from-newer-build`. Upgrading
  everyone who shares a store is the shorter path.
- **Run `docir reindex` after upgrading**, or `docir self upgrade`, which does it for you.

## The upgrade that timed out while the daemon was still working

`docir self upgrade` runs `reindex --resync`, and after the package step that is always the full
pass — the step is what made the build stamp unequal. Its cost is the size of the corpus. The
client gave up at 300s while the daemon completed the rebuild and committed it, which left an
error, a rebuilt store, instruction files that were never refreshed, and no `check` report. Past
roughly 1,500 documents the command could not succeed at all.

The daemon now sends a keepalive frame while a request runs and the client discards them, so the
budget measures silence rather than work. A wedged or killed daemon still fails, and now says so
in those terms instead of advising a bigger number.

```
docir self upgrade
docir daemon status
```

Verified against this repository's own corpus over both transports: 146s of rebuild completed
under an 8s reply budget.

## Vectors know what they were computed from

A full rebuild re-saves every document, which queues every one for embedding, and the drain
recomputed all of them — 1,547 vectors and 146s against 205 documents, on a release that had
changed nothing the model reads.

Each row now records a digest of what produced it: the model id, the document's embedding text,
and every chunk it would be split into. The drain compares it and skips a document whose inputs
are unchanged. The same upgrade against the same corpus now costs **2.6s**, and a single
hand-edited file still reports exactly one re-embed.

```
docir reindex
docir embed --flush
```

A chunking change still forces the full recompute, by itself: different splitting is a different
set of chunks and so a different digest, with no version constant for anyone to remember to
bump. The skip also requires the stored chunk count to match, because chunks live in their own
table and are dropped by their own calls — a matching digest alone would have made `docir
reindex` stop being the repair for a wiped chunk set.

`docir reindex` therefore reports `0` re-embedded for a corpus nobody has edited. The document
count is unchanged: a rebuild still re-reads every file.

## Full changelog

See [CHANGELOG.md](https://github.com/l0kifs/docir/blob/v0.25.0/CHANGELOG.md).
