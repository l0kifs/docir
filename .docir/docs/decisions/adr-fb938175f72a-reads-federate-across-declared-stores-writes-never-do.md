---
code:
- src/docir/entry_points/federation.py
created: '2026-08-12'
description: Why docir reads fan out across a committed list of peer stores, why peers
  are opened read-only, and why the merge sorts on similarity rather than score.
id: adr-fb938175f72a
related:
- kind: refines
  to: adr-20eec6e2e2ca
status: accepted
tags:
- architecture
- cli
- retrieval
title: Reads federate across declared stores; writes never do
type: decision
updated: '2026-08-17'
---

## Context

adr-20eec6e2e2ca gave docir a project-local store and closed with an explicit
exclusion: *"no multi-store federation/search across stores — one resolved store
per invocation."* That is the right default and the wrong ceiling. In a
multi-repo organisation the decision governing the service you are editing lives
in the platform repo, and an agent reading `context` in the service repo cannot
see it — so it re-decides. DocHub's answer is a root manifest that consolidates
many repositories; docir had nothing.

The constraint that shapes every option: **a peer store belongs to someone
else.** Its index is derived and gitignored, its schema may use different
profiles, and nothing gives this process the right to write to it.

## Decision

Reads fan out across a declared set of peer stores. Writes never do.

### The peer list is a committed file

`.docir/stores.yaml`, beside `docs-schema.yaml`, holding a list of store homes.
Relative paths resolve against this store's home, so a file committed by one
person works for everyone who clones the same layout. `--store PATH` (repeatable)
adds one for a single invocation; it does not replace the file's list. The list
is read per request rather than at daemon startup — it is one small file, and a
daemon that had cached it would answer from a set the reader had already edited.

Rejected: an env var (`DOCIR_STORES`) — nothing about it is shareable with the
team, which is the whole point; and walking up for sibling `.docir/` directories
— a store would join your reads because of where it sits on disk, which is
exactly the kind of implicit resolution `docir init` was written to remove.

### Peers are opened read-only, at the database

A peer engine's URL is `sqlite:///file:<path>?mode=ro&uri=true`. SQLite then
refuses a write with `attempt to write a readonly database`, so "docir does not
write to a peer" is enforced by the database rather than promised by a comment.
Nothing else would be sufficient: `build_container` runs migrations and ensures
directories, both of which write, so peers get their own reader construction
path that does neither.

A peer is **unavailable** — never an error, never a silent empty result — when
its home is missing, has no `index.db`, or fails to open (an index older than
this docir's migrations reads as exactly that). The read proceeds without it and
says so on stderr, naming the store and the command that fixes it, the way the
global-fallback warning already does. An unavailable peer must not fail the
read: the whole point is that a peer is someone else's repository, and its state
is not this reader's problem to resolve.

### Only four commands fan out

`get`, `query`, `search`, `context`. `FEDERATED_COMMANDS` is asserted against
`Dispatcher._handlers` in the suite, so a new command reaches federation by a
decision rather than by omission — the same guard the MCP tool names have.

Every write, every maintenance command and `build` stay local. `check` in
particular: a peer's dangling edges are not this repository's to report, and
`--fix` would repair someone else's corpus.

### Merging is by similarity, never by score

`score` is reciprocal-rank fusion, so it says where a document placed **within
its own store's ranking**. A two-store probe makes the trap concrete: a document
with `similarity 0.0` scored `0.0164` against another store's `similarity 0.378`
scoring `0.0328` — the ordering those scores imply is an artifact of how many
documents each store held. `similarity` is a raw cosine against the query and is
the one number comparable across stores, which is what the merge sorts on.

Hits carrying no `similarity` (lexical-only, or reached through the graph) are
appended after the scored ones, round-robin across stores in each store's own
order. Absent still means *not scored*, never zero — dropping them would filter
on embedding-queue state, and sorting them as 0.0 would rank them below a
genuinely irrelevant match. The local store wins ties. The merged list is then
truncated to `limit`, so `--limit` keeps meaning "this many documents".

A cross-store re-fusion of the raw rankings was the alternative. It is arguably
more correct and it requires the fan-out to live inside `indexing`, which would
make every store's candidate list one query's working set; that is a different
and much larger change, and it can supersede this one on evidence.

### `store` is stamped per row only while federating

The read paths deliberately carry no `store` field: it is one absolute path,
identical for every row, and per-row it costs more than the field is worth. That
argument holds exactly while there is one store. With peers, the path is the
only thing distinguishing two hits, so every row carries `store` — and a
single-store read stays byte-identical to what it returns today. Ids remain the
only identifier; `store` disambiguates a collision rather than qualifying the id.

`get` tries the local store first and then each peer in order, first match wins.

## Consequences

- Supersedes the federation exclusion in adr-20eec6e2e2ca. Store *resolution* is
  unchanged — there is still exactly one home per invocation, and it is still the
  only one written to.
- Each peer costs an engine and a schema load; the embedder is shared with the
  primary, so the model is still loaded once per process.
- A peer with a different schema is read as it is. Its types and statuses are
  whatever that store declared, and this store's `check` says nothing about them.
- Cross-store relation edges remain impossible: Tier 0 validates a `related`
  target against the local store, and an edge that could point anywhere would
  make `dangling` unanswerable.
- `--limit` against N stores asks each for `limit` and truncates the merge, so a
  federated read costs N times the work of a local one.

## Measurement (2026-08-12)

Measured on docir's own benchmark corpus (26 documents, 20 tasks, k=5,
`bge-small-en-v1.5`) by splitting it alternately into two stores and asking
every task of both, `benchmarks/federation.py`:

| strategy | recall@5 | MRR |
|---|---|---|
| single store (the ceiling) | 0.97 | 0.97 |
| split · merge on **similarity** | 0.91 | 0.93 |
| split · merge on rank (cross-store RRF) | 0.88 | 0.72 |

Two things follow, and the second is why the alternative is now closed rather
than deferred.

**Cross-store RRF over the lists the stores return *is* round-robin.** RRF sums
`1/(k + rank)` across the lists a document appears in; each document lives in
exactly one store, so every sum has one term and the fused order is rank
position alone. Ordering by similarity beats it on both metrics and by 21 points
of MRR — the number that says whether the right document arrived *first*, which
is the whole job of a ranked read for an agent that will read two or three of
them.

**A split costs about six points of recall no matter how it is merged**, and
most of that is the graph rather than the ranking: 8 of the corpus's 17 edges
cross the split, and an edge cannot cross stores because Tier 0 validates a
`related` target locally. That cost belongs to federating at all, not to this
choice, and it is the ceiling any future re-fusion would have to beat.

Re-fusing the *raw* lexical and vector rankings — which needs the fan-out to
live inside `indexing` — remains untested and remains the only version of the
alternative that could still supersede this decision.

## Amendment: build is single-store (2026-08-13)

`docir build` renders one store's corpus, and that is now explicit rather than
incidental. The build is assembled from `query` plus one `get` per document —
both federated commands — so a store declaring peers published their documents
into this repository's site while the summary line still named this store. The
CLI opts that pair out with a `local_only` payload key, which the fan-out reads
before anything else.

An empty `stores` list could not carry that meaning: the MCP tools send one
whenever the argument is omitted, and a declared `stores.yaml` must still apply
there.

Why single-store is the right answer rather than a flag:

- A published page is a **copy**, and a copy of a peer's decision goes stale the
  moment that repository edits it. That is the failure the staleness model exists
  to prevent, and nothing in the site could detect it — `verified` means a human
  re-read the document in *its own* store.
- The peer publishes its own site. The useful cross-repository artifact is a
  link, not a duplicate, and a link needs the peer's site URL, which this store
  does not know.
- `--out` is regenerated wholesale, so the copies would also be silently
  re-created on every build, each time from whatever the peer's index happened
  to hold.

`check`, `reindex` and every write were already local; this closes the one read
path whose *output is written to disk* rather than answered to a caller.

## A peer older than this build is skipped

Peers are never migrated, so an index can be at any revision docir ever shipped, and every
table or column a migration adds is one some peer will not have. It broke twice before anyone
noticed the pattern: `mentions` (0008) took down `context` and `get`, `document_code.digest`
(0007) took down every hydrate and so `query` as well. Through the daemon the user saw only
"daemon closed the connection without responding".

`peer_status` compares the peer's `alembic_version` against this build's head, so one rule
covers every past and future migration. Guarding each column as it was added also worked, and
had to be remembered — which is the failure mode itself.

Three properties hold it up. A revision this build does not recognise is from a **newer** docir
and is allowed: every query names its columns, so extra ones read fine, and refusing would make
upgrading one repository break every repository that had not upgraded yet. A **missing**
revision is skipped, because "cannot say" is not permission to proceed. And the skip reuses the
existing warn-and-carry-on path, so an unreadable peer still never fails the caller's own query.

The cost is real: upgrading docir darkens every peer until each is reindexed. The message names
both revisions and the command that fixes it, which is the trade against a stack trace naming a
column.
