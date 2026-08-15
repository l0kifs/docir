---
created: '2026-08-15'
description: 'How a store federates reads over declared peers: stores.yaml, --store,
  why writes and build never federate, and why ranking merges on similarity.'
id: run-45b267a709b4
owner: maintainer
related:
- adr-fb938175f72a
status: active
tags:
- retrieval
- cli
title: Read across repositories
type: runbook
updated: '2026-08-15'
---

The decision that governs the service you are editing often lives in another repo, and
an agent that cannot see it re-decides. Federation lets one store answer reads from
several.

## Declare the peers

A store declares the peers it reads in `.docir/stores.yaml` — committed, so the set is
the team's rather than each machine's:

```yaml
stores:
  - ../platform/.docir       # relative to this store, so a clone works unchanged
  - ~/work/shared/.docir
```

`docir context`, `query`, `search` and `get` then answer from all of them, and every
row names the `store` it came from. That field is only present while federating; with
one store it is pure cost, which is why the read paths never carried it before.

## Adding a peer for one command

`--store <path>` adds a peer for a single invocation without touching the committed
set. The four MCP read tools take the same thing as a `stores` argument, so an agent
that only speaks MCP is not stuck with whatever the repo committed.

## Writes never federate

`add`, `update`, `check` and `reindex` see only the resolved home. There is still
exactly one store you can write to, and `build` is single-store for the same reason: a
published copy of a peer's decision would age the moment that repo edits it.

## Peers are opened read-only

The connection carries SQLite's `mode=ro`, so a write is refused by the database rather
than avoided by convention. It also means a peer gets its own construction path — the
normal one runs migrations and creates directories, and a peer is another repository,
not yours to migrate.

## A peer that cannot be read is skipped, not fatal

A peer's index is derived and gitignored, so a colleague's fresh clone has none.
Failing the read would make that everyone's outage. docir warns on stderr and answers
from the rest.

## Ranking merges on `similarity`, never `score`

`score` is a reciprocal-rank fusion *within one store*, so comparing two stores' scores
compares corpus sizes rather than relevance. The merge sorts on `similarity`, the raw
cosine, which means the same thing everywhere. Hits with no vector yet are appended
round-robin rather than treated as 0 — absent means *not scored*, not *scored zero*.

## Which commands federate

Exactly `get`, `query`, `search` and `context`. The list is asserted against the
dispatcher's command table in the test suite, so a new command joins by decision rather
than by omission.
