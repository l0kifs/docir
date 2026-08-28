---
code:
- src/docir/entry_points/federation.py
created: '2026-08-28'
description: Why a store describes itself in its own stores.yaml, and why that sentence
  rides on every federated row beside the store path.
id: adr-84fb02d5061b
owner: maintainer
related:
- kind: refines
  to: adr-fb938175f72a
status: accepted
tags:
- architecture
- cli
- retrieval
title: Federated rows carry the store's own description
type: decision
updated: '2026-08-28'
---

## Context

adr-fb938175f72a made a federated row name the store that answered it, because
with peers the path is the only thing separating two hits. That is all a path
can do. It says *which* repository, and the judgement a reader actually has to
make about a hit from somewhere else is a different one: is that corpus the one
that governs what I am doing?

`/Users/me/work/platform/.docir` does not answer it. Neither does the directory
name — `platform`, `core`, `shared` are what repositories are called, not what
they hold. So an agent reading a federated result either trusts a hit from a
corpus that has no authority over its task, or discounts one from the corpus
that decides it. Both failures are silent, and both look like bad retrieval.

## Decision

A store describes itself, in one string, in its own `.docir/stores.yaml` beside
the peers it reads:

```yaml
description: Platform decisions every service must follow.
stores:
  - ../platform/.docir
```

Every row that store answers while federating carries `store_description`
beside `store` — `query`, `search`, `context`, and both shapes of `get`. The
key is optional and independent of `stores:`, so a corpus that reads no peers
still describes itself to every reader pointing at it.

## Why the store describes itself

The alternative is the reader annotating each peer it declares, which is the
smaller change and the wrong one. The same sentence is then written once per
repository pointing at that corpus, every copy drifts as the corpus changes,
and the writer is the party who knows it least well.

It also cannot label the reader's *own* rows. A federated read merges the local
store's hits with its peers', and those rows are stamped too — under a
reader-side annotation the one corpus with no description would be the one the
agent is standing in.

The cost is one small file read per answering store per request, deliberately
not cached, for the reason the peer list is not: a daemon would otherwise serve
a description its owner has already rewritten.

## Absent, never empty

A store that describes itself nowhere omits the field rather than sending `""` —
an empty string reads as *this corpus is about nothing* rather than *nobody
wrote a description*. A single-store read carries neither `store` nor
`store_description`, unchanged from adr-fb938175f72a: describing yourself is
for telling another reader what this is, and a store with no peers is talking
to nobody.

A peer whose `stores.yaml` is malformed loses its label and not the read, the
same asymmetry an unavailable peer already has — a peer is someone else's
repository. This store's own file keeps no such tolerance: it is parsed on the
same request by the peer list, and a broken one raises.

## Consequences

- `stores.yaml` gains a second recognised key, so an unrecognised one is now
  refused by name. Until now a file with no `stores:` key was itself an error,
  which is what caught `store:` for `stores:`; a description-only file is
  legitimate, so the typo needs its own refusal.
- **Every example ships `stores:` alongside `description:`, `[]` when there are
  none.** docir 0.20.0 and earlier refuse a `stores.yaml` without that key —
  `peer_homes` raises before the read — so a description-only file takes
  `context`, `query`, `search`, `get` and `doctor` down for everyone in that
  repository who has not upgraded, while writes keep working. Verified against
  the published 0.20.0 on stores it built. Nothing this build does can fix an
  older reader, so the spelling is the fix, and a test pins it in the shipped
  example.
- No index or schema change: the description is read from the file on every
  request, so nothing migrates and nothing needs a reindex. Verified both ways
  against 0.20.0 — this build reads an index it built without a reindex, and
  0.20.0 federates into a store this build describes, ignoring the key.
- `docir doctor` reports what this store says it is and what each declared peer
  says it is, which is where a description that never arrives becomes visible
  without staging a query that happens to hit that corpus.
- Nothing verifies a description. It is prose about a corpus, and a wrong one
  misleads exactly as a wrong `description:` on a document does.
