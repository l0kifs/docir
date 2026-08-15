---
created: '2026-08-15'
description: 'How a query becomes results: full-text and vector rankings fused, section-level
  embeddings, default status visibility, and reads spanning peer stores.'
id: arch-03eeae8bf37d
related:
- kind: refines
  to: arch-1cfb1b212237
status: active
tags:
- architecture
title: Doc-Index CLI — the read path
type: architecture
updated: '2026-08-15'
---

## Read path

Agent → `docir context "<task>"` → hybrid scoring (FTS5 + semantic) +
related-graph traversal → returns a small relevant subset instead of the
whole `docs/` folder.

**Two-tier retrieval (skeleton → body).** `context`, `query`, and `search`
return *skeletons* — frontmatter, tags, typed `related`, and the
`owner`/`verified`/`stale` fields, but **not the body**. The agent scans those to
judge relevance and then fetches only the bodies it needs with `docir get <id>`.
Keeping bodies out of result sets is where the context savings come from; the
`description` field (indexed and shown in listings) is what makes the skeleton
enough to judge relevance.

## Semantic layer (fastembed)

Pure FTS5 misses semantically close but lexically different matches (e.g.
a query about "refresh token handling" against a document titled "session
renewal strategy"). `fastembed` (ONNX-based, quantized, CPU-only, no
external API call — consistent with the project's privacy-first stance
elsewhere) closes this gap without pulling in heavy ML dependencies.

### Storage

a document vector over `title` + `description` + body,
**plus one vector per `##` section** — see "Semantic index: every section
is embedded" below for why the document vector alone was not enough. Both
are BLOBs in SQLite; each row records the model that produced it, so
switching embedder recomputes rather than comparing vectors of different
widths. The agent-authored `description` gives the document vector a
concise, high-signal summary to anchor on, improving retrieval over
embedding raw body text alone. Brute-force cosine similarity is sufficient
at this scale (hundreds to low thousands of documents) — no ANN index
needed.

### docir context scoring

combines FTS5 BM25 score and cosine
similarity (e.g. weighted sum or reciprocal rank fusion) rather than
replacing FTS5 outright — lexical matches are still valuable and cheap.

### Where it runs

entirely inside the daemon (see above), so the model
is loaded once and reused; per-call added latency is on the order of
single-digit to tens of milliseconds, not the cold-start cost of loading
the model fresh.

### Recompute triggers

the embedding is tied to *what changed*, not to
every `docir update` call — recomputing on metadata-only changes (e.g. a
status transition) would be wasted work with no benefit:
- `docir add` → embedding scheduled (new document).
- `docir update` changing `title`, `description`, or the body
  (`--append-section`, `--replace-section`, `--replace-body`) →
  embedding scheduled.
- `docir update` touching only other frontmatter fields (`--status`,
  `--tags`, `related`) → embedding left untouched.
- `docir archive` / deletion → the vector is removed from the index along
  with its FTS and relation rows, so an archived/deleted document can't
  resurface via similarity search or Tier 2 DRY checks.

### Async recompute (not on the write's critical path)

an agent rarely
writes a document in a single call — it does `docir add` then several
`--append-section` edits over a long session. Recomputing the vector
synchronously on each write would re-embed the same document repeatedly
and put model inference on the write path, serializing the agent's rapid
successive calls behind it. Instead, two levels of consistency are
separated:
- **Synchronous, immediately consistent:** file write, metadata, FTS5,
  relations. Cheap, and search correctness depends on it — ready by the
  time the command returns.
- **Deferred, eventually consistent (embeddings only):** a content
  change sets an `embedding_dirty` flag on the row (persisted in SQLite,
  so it survives a daemon crash/restart) and returns immediately. A
  background worker inside the daemon drains dirty rows with a short
  **debounce** window (a few seconds), coalescing a burst of edits to
  one document into a single recompute.

### Consistency window

between the write and the vector being ready, the
document is still found via FTS (lexically) — the semantic contribution
simply joins a few seconds later. A brand-new document is FTS-only until
its vector lands; an updated one temporarily keeps its previous vector.
On daemon restart, the worker re-embeds anything still flagged dirty, so
nothing is silently lost.

### Escape hatch

`--wait-embeddings` on a write, or `docir embed --flush`,
forces a synchronous recompute when a semantically-heavy query must run
immediately afterward (e.g. in tests).

### Model version changes

if the embedding model is upgraded, existing
vectors become stale; `docir reindex --embeddings` recomputes them all,
same fallback pattern as the existing `docir reindex`.

### Also powers Tier 2 DRY linting

(`docir lint --deep`): the same
vectors are reused to flag content-similarity across documents, so
there's no duplicate infrastructure for search vs. lint.

## Semantic index: every section is embedded

The embedding model (`bge-small-en-v1.5`) reads about 512 tokens — roughly
1,900 characters of prose — and silently ignores the rest: appending text past
that boundary returns a bit-identical vector. 84 of docir's own 103 documents at
the time of measurement exceeded it, so more than half the corpus was absent
from the semantic index while FTS5 hid the problem by covering the whole body.

So the embedding pass writes a document vector **and one vector per `##`
section** (`chunk_embeddings`, keyed `(doc_id, ordinal)`). The scorer accepts
repeated ids from the semantic ranking and keeps each document's **best**
chunk — RRF fuses rankings *of documents*, so the collapse has to happen before
fusion, not after. The winning candidate survives the collapse, not just its
score, which is what lets a ranked hit name the heading that matched
(`matched_section`) and an agent read only that span with
`docir get <id> --section "<heading>"`.

Load-bearing details:

- `MAX_CHUNK_CHARS` (1200) is *derived* from the measured window, not chosen —
  and each chunk carries the document title as a prefix, which eats into the
  budget. A chunk allowed to overflow reintroduces the original bug one level
  down.
- The splitter tracks fenced code blocks, because a `##` comment inside one is
  not a heading, and cutting there yields two invalid chunks.
- There is **no second dirty flag**: chunks are rewritten wholesale under the
  existing `embeddings.dirty` queue, in the same transaction.
- Tier 2 similarity linting deliberately still compares *document* vectors only.
  Chunk vectors would answer "do these two share a section", not "are these the
  same document".
- `indexing` may not import `documents`, so the entity is the seam:
  `Document.embedding_chunks()` hands the scheduler positional
  `(ordinal, heading, text)` triples.

Because max-pooling structurally favours documents with more sections, the
recall gate on the benchmark corpus is not optional — keep it when touching
ranking.

## Status filtering (default visibility)

Closed documents are not deleted or hidden physically — they stay in `docs/`, in
git history, and remain fully queryable. Visibility is controlled purely at the
read path:

- `docir context`, `docir query` and `docir search` filter to active statuses by
  default. "Closed" is per type, not one hardcoded status: each type declares
  its own `inactive_statuses` — `superseded`/`rejected` for a decision,
  `resolved` for an issue, `deprecated` for architecture.
- `--include-inactive` widens any of them, and `docir get <id>` always returns
  the document whatever its status — an agent checking whether a similar bug was
  already fixed needs exactly that. (`--include-resolved` is the old spelling,
  still accepted; it named a status only two types have.)
- `docir archive` goes further, removing a document from active search entirely
  (see "Archiving vs. deletion") — for volume rather than for status.

**There is exactly one visibility predicate, and expansion runs both ways.**
`DocumentService._is_visible` (archived + inactive status) is called by the
ranked fusion loop *and* by the graph-expansion pass; do not inline the check
into either. They used to differ — expansion tested only `archived` — so a
resolved issue the caller had excluded came back through a neighbour edge, and
the filter that held on three read paths leaked on the fourth.

Expansion follows outgoing edges **and** incoming *successor* edges, successors
first in each seed's list. A `supersedes` edge points from the new document to
the old one, so before this the replacement sat one hop away *backwards* and the
graph could not answer "is this decision still current?" — the question it exists
for. Which kinds count is schema data (`successor: true`), not a hardcoded pair,
so a custom kind with that shape is followed too.

Down-weighting closed documents in scoring instead of excluding them was
considered and not built: a status filter is a statement about whether a document
is current, and a score is a statement about relevance. Blending them makes
neither answerable.

## Reading across stores

In a multi-repo organisation the decision governing the service you are editing
often lives in the platform repo, and an agent reading `context` in the service
repo cannot see it — so it re-decides. `.docir/stores.yaml`, committed beside
`docs-schema.yaml`, declares peer store homes; `--store PATH` (repeatable) adds
one for a single invocation **on top of** that list, without editing the file.
Relative paths resolve against this store's home, so a file one person commits
works for everyone who clones the same layout, and the list is read per request
rather than cached at daemon startup.

**Reads federate; writes never do.** Exactly four commands fan out —
`get`, `query`, `search`, `context` — and that set is asserted against the
dispatcher's own command list in the suite, so a new command joins by decision
rather than by omission. Every write and every maintenance command runs against
the local store alone.

Three properties are load-bearing:

- **Peers are opened read-only at the database**
  (`sqlite:///file:<path>?mode=ro&uri=true`), so "docir does not write to a
  peer" is enforced by SQLite rather than promised by a comment. This is also
  why peers get their own construction path: the normal container build runs
  migrations and creates directories, both of which write.
- **An unreadable peer is skipped with a warning on stderr, never an error.** A
  peer's index is derived and gitignored, so a fresh clone of it simply has
  none; failing the read would make one repository's state everyone's outage.
- **The merge sorts on `similarity`, never `score`.** RRF ranks *within* one
  store, so comparing two stores' scores compares the sizes of their corpora.
  Rows carry a `store` field only while federating — it is pure cost with one
  store, which is why the read paths never carried it before.
