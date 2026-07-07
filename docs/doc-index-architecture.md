# Doc-Index CLI — Architecture

## Principle

Git is the source of truth. The database is a derived, read-optimized index
built on top of the markdown files. No data lives uniquely in the database —
it can always be rebuilt from the files. AI agents never edit markdown files
directly; all writes go through the CLI to guarantee schema consistency.

## Diagram

```
┌─────────────────┐
│   docs/*.md       │  ← source of truth, versioned by git
│  (frontmatter +    │     + docs/tags.yaml (tag registry)
│   markdown body)   │
└────────┬─────────┘
         │ index / reindex
         ▼
┌─────────────────┐
│  SQLite index      │  ← derived layer, .gitignore
│  - docs (metadata)  │
│  - relations (graph)│
│  - FTS5 (full text)  │
│  - embeddings (BLOB) │
└────────┬─────────┘
         │
         ▼
┌─────────────────┐
│  Daemon (worker)   │  ← long-lived: owns DB connection, warm
│  - serves requests  │     embedding model, async embed queue
│  - embed queue      │
└────────┬─────────┘
         │ Unix socket
         ▼
┌─────────────────┐
│   CLI (Typer)       │  ← thin client, single entry point
│  get/query/search/   │     spawns daemon on first use
│  context/update/add  │
└────────┬─────────┘
         │
         ▼
     AI agent (Claude Code)
```

## Layers and responsibilities

| Layer | Responsible for | Not responsible for |
|---|---|---|
| Files (.md) | Content storage, git history, human readability | Fast search, structured queries |
| SQLite index | Search, filtering, relation graph, embeddings | Storing unique data |
| Daemon | Warm embedding model, async embed queue, request serialization | Being user-visible; holding canonical data |
| CLI | Agent contract, single write path, frontmatter consistency | Project business logic |

## Daemon process

The CLI remains a thin, stateless client from the user's/agent's
perspective (`docs <command> ...`), but underneath it delegates to a
long-lived local background worker instead of doing heavy work cold on
every invocation.

**Why:** the dominant cost of adding a semantic layer (see below) is not
the embedding computation itself but reloading the ONNX model into memory
on every single process start — hundreds of milliseconds to over a second
per call if done cold. A persistent process keeps the model warm and
avoids paying that cost per command.

**Lifecycle:**

1. On first invocation of any `docs` command, the CLI checks for a running
   daemon (e.g. a PID file + local Unix socket at a fixed path such as
   `~/.cache/docs-cli/daemon.sock`).
2. If not running, the CLI spawns it as a detached background process,
   waits for the socket to become ready, then proceeds.
3. All subsequent commands (in this session or later ones) connect to the
   existing socket directly — no spawn, no model reload.
4. The daemon owns: the SQLite connection, the loaded embedding model, and
   the in-memory FTS/graph structures it may cache. It is responsible for
   handling one request at a time or a small connection pool — write
   operations are serialized here, which also naturally resolves most
   write-conflict races without extra file locking.
5. The daemon is disposable: if it's not running, is killed, or the socket
   is stale, the CLI transparently respawns it. No command should ever
   hard-fail just because the daemon wasn't up yet.
6. An idle timeout (e.g. shut down after N minutes of inactivity) keeps it
   from lingering forever as a forgotten background process.

This keeps the "just run `docs ...`" UX simple for the user/agent — the
daemon is an implementation detail, never something they need to manage
manually (though `docs daemon status` / `docs daemon stop` are useful
escape hatches).

## File format

```yaml
---
id: adr-0007
title: Auth strategy
description: How the service authenticates API clients and refreshes tokens.
type: decision
status: accepted
tags: [auth, api]
related: [adr-0003, issue-12]
created: 2026-06-15
updated: 2026-06-30
---
```
Body: standard markdown, human-readable, diffs cleanly in git.

### Frontmatter fields

| Field | Required | Set by | Description |
|---|---|---|---|
| `id` | yes | `docs add` (auto-generated) | `<type-prefix>-NNNN`, generated from the next free number in the index — never chosen manually, avoids collisions between parallel agents |
| `title` | yes | `docs add`, `docs update --set-field title` | Canonical document title. Frontmatter-only source of truth; the CLI never enforces or generates a body heading from it |
| `description` | yes | `docs add`, `docs update --set-field description` | One- or two-sentence summary of the document, written by the agent at creation and kept current on meaningful edits. Feeds search quality — indexed in FTS and included in the embedded text — and shown in `docs query`/`docs context` result listings so the agent can judge relevance without fetching the full body |
| `type` | yes | `docs add` (fixed at creation) | Document type (`decision`, `issue`, `architecture`, ...); determines which schema/status enum from `docs-schema.yaml` applies |
| `status` | yes | `docs add` (default), `docs update --status` | Type-specific enum (e.g. `decision`: proposed/accepted/rejected/superseded; `issue`: open/resolved). Transitions are validated against `docs-schema.yaml` |
| `tags` | no | `docs add --tags`, `docs update --set-field tags` | List of tag keys for `docs query --tag` filtering. Each key must exist in the tag registry (Tier 0 validation) — free-form tags are rejected, preventing synonym sprawl |
| `related` | no | `docs add --related`, `docs update` | List of other document ids this one links to; forms the relation graph used for traversal and Tier 1 graph checks |
| `created` | yes | `docs add` (auto) | Set once, never modified afterward; used for audit/sort queries |
| `updated` | yes | CLI (auto, every write) | Refreshed on every `docs update`, metadata or body |
| `archived` | no | `docs archive` / `docs unarchive` | Absent by default; `true` removes the document from active search (FTS, embeddings) while keeping the file and index rows |

`created` is set once by `docs add` and never modified afterward. `updated`
is refreshed by the CLI on every `docs update` call (metadata or body). The
distinction matters for Tier 1 checks (e.g. a recently created orphan doc
vs. a long-standing one are different signals) and for audit queries like
"decisions made last quarter", which should sort on `created` rather than
`updated`.

`title` is stored only in frontmatter — it is the canonical source used by
the index for listings, `docs query`, and `docs context` results. The CLI
does not enforce or auto-generate any heading in the body; the agent
decides what (if anything) to write there, including whether to repeat the
title as an `# H1`.

`archived` is an optional frontmatter field, absent by default and set to
`true` only by `docs archive` (removed again by `docs unarchive`) — see
"Archiving vs. deletion" below.

### Tag registry

Tags are not free-form strings — they are registered entities, each with a
unique key and a description. The registry is the source of truth for what
tags exist, versioned in git like everything else (a `docs/tags.yaml`
mapping key → description; promotable to a full tag doc-type later if tags
need their own relations/history).

```yaml
# docs/tags.yaml
auth:    "Authentication, authorization, tokens, sessions."
api:     "Public/internal HTTP API surface and versioning."
storage: "Persistence, database schema, migrations."
```

- **Referential integrity (Tier 0):** every key in a document's `tags`
  must exist in the registry. An unknown tag is a hard error at
  `docs add`/`docs update` time — "unknown tag, register it first" — the
  same guarantee applied to `related` ids. This eliminates the main
  failure mode of free-form tags: synonym sprawl (`auth`,
  `authentication`, `Auth`) fragmenting the same concept.
- **Descriptions feed search:** a tag's description is available to
  `docs context` so the agent (and the semantic layer) can reason about
  what a tag means, not just match the bare key.
- **CLI:** `docs tag add <key> --description "..."`, `docs tag list`,
  `docs tag rename <old> <new>` (rewrites the key across all referencing
  documents), `docs tag rm <key>` (blocked while any document still uses
  it, unless `--force`). Unlike a dangling `related` id, a `--force` tag
  removal does not leave broken keys behind: since a tag is a classifier
  rather than a link, the CLI strips the removed key from the `tags` list
  of every referencing document (rewriting those files and reindexing
  them) as part of the same operation.

## Write path

Agent → `docs update` / `docs add` → CLI validates schema → writes to the
.md file → CLI updates that single file's index rows (metadata, FTS5,
relations) synchronously in the same command call, and schedules the
embedding recompute asynchronously (see Semantic layer). Everything except
the embedding is current the moment the command returns; the embedding
follows within seconds.

### Document creation (`docs add`)

```
docs add --type decision --title "Refresh token rotation" \
  --description "When and how refresh tokens are rotated on renewal." \
  --tags auth,api --related adr-0007 \
  --body-file draft.md
```

Steps performed by the CLI:

1. Generate `id` as `<type-prefix>-NNNN`, using the next free number from
   the database (not by scanning files — avoids race conditions between
   parallel agents).
2. Assemble frontmatter from arguments plus type defaults (e.g.
   `status: draft` for `decision`, `status: open` for `issue`) and
   auto-set `created` and `updated` to today.
3. Validate: required fields per type (including `title` and
   `description`, which the agent must supply at creation), `status` must
   be a valid enum value for that type, every id in `related` must already
   exist in the index.
4. Accept the body via `--body-file`, `--body "text"` for short content,
   or `--stdin` — the most agent-friendly option, avoiding shell-escaping
   issues with multi-line markdown.
5. Write the physical file to `docs/<type>s/<id>-<slug>.md`.
6. Synchronously index it: `INSERT` into `docs`, `relations`, and FTS5,
   and flag the row for embedding (computed asynchronously — see Semantic
   layer).
7. Return the generated `id` and file path to the caller, so the agent can
   reference the new document later in the same session.

### Document editing (`docs update`)

Two distinct operations, kept separate rather than merged into one:

- **Metadata update** (frequent, low-risk):
  `docs update issue-12 --status resolved` — patches only specific
  frontmatter fields, body untouched. `--set-field title "..."` /
  `--set-field description "..."` update those fields the same way.
- **Body update** (higher-risk) — three supported modes:
  - `--append-section "Resolution" --body "Fixed in PR #42"` — appends a
    new heading/section at the end without touching existing content.
    **Default, safest path** — fits patterns like "issue closed → note how".
  - `--replace-section "<heading>" --body "..."` — replaces content under
    a specific existing heading.
  - `--replace-body --force` — full body replacement. Requires an explicit
    force flag because it can silently overwrite content the agent never
    read in full; agents should `docs get` first.

When a body edit changes what the document is fundamentally about, the
agent is expected to update `description` in the same call (e.g.
`--append-section ... --set-field description "..."`), keeping the summary
that drives search in step with the content — the same discipline applied
to `title`.

### Write conflict handling

Before writing, the CLI checks whether the file's `updated` timestamp/hash
changed since the agent last fetched it (or since the command started). If
it changed:
- Append/section operations attempt a straightforward merge (safe in most
  cases).
- Full-body replace fails with a "stale write, refetch" error rather than
  silently overwriting.

### Per-type schema

Required fields, valid status enums, and allowed status transitions (e.g.
`open → resolved`, not the reverse without an explicit override) are
defined in a `docs-schema.yaml` config, not hardcoded in the CLI — new
document types can be added without changing CLI code.

## Read path

Agent → `docs context "<task>"` → hybrid scoring (FTS5 + semantic) +
related-graph traversal → returns a small relevant subset instead of the
whole `docs/` folder.

### Semantic layer (fastembed)

Pure FTS5 misses semantically close but lexically different matches (e.g.
a query about "refresh token handling" against a document titled "session
renewal strategy"). `fastembed` (ONNX-based, quantized, CPU-only, no
external API call — consistent with the project's privacy-first stance
elsewhere) closes this gap without pulling in heavy ML dependencies.

- **Storage:** one embedding vector per document, computed over its
  `title` + `description` + body, stored as a BLOB column in SQLite
  alongside existing metadata. The agent-authored `description` gives the
  vector a concise, high-signal summary to anchor on, improving retrieval
  over embedding raw body text alone. Brute-force cosine similarity is
  sufficient at this scale (hundreds to low thousands of documents) — no
  ANN index needed.
- **`docs context` scoring:** combines FTS5 BM25 score and cosine
  similarity (e.g. weighted sum or reciprocal rank fusion) rather than
  replacing FTS5 outright — lexical matches are still valuable and cheap.
- **Where it runs:** entirely inside the daemon (see above), so the model
  is loaded once and reused; per-call added latency is on the order of
  single-digit to tens of milliseconds, not the cold-start cost of loading
  the model fresh.
- **Recompute triggers:** the embedding is tied to *what changed*, not to
  every `docs update` call — recomputing on metadata-only changes (e.g. a
  status transition) would be wasted work with no benefit:
  - `docs add` → embedding scheduled (new document).
  - `docs update` changing `title`, `description`, or the body
    (`--append-section`, `--replace-section`, `--replace-body`) →
    embedding scheduled.
  - `docs update` touching only other frontmatter fields (`--status`,
    `--tags`, `related`) → embedding left untouched.
  - `docs archive` / deletion → the vector is removed from the index along
    with its FTS and relation rows, so an archived/deleted document can't
    resurface via similarity search or Tier 2 DRY checks.

- **Async recompute (not on the write's critical path):** an agent rarely
  writes a document in a single call — it does `docs add` then several
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

- **Consistency window:** between the write and the vector being ready, the
  document is still found via FTS (lexically) — the semantic contribution
  simply joins a few seconds later. A brand-new document is FTS-only until
  its vector lands; an updated one temporarily keeps its previous vector.
  On daemon restart, the worker re-embeds anything still flagged dirty, so
  nothing is silently lost.

- **Escape hatch:** `--wait-embeddings` on a write, or `docs embed --flush`,
  forces a synchronous recompute when a semantically-heavy query must run
  immediately afterward (e.g. in tests).
- **Model version changes:** if the embedding model is upgraded, existing
  vectors become stale; `docs reindex --embeddings` recomputes them all,
  same fallback pattern as the existing `docs reindex`.
- **Also powers Tier 2 DRY linting** (`docs lint --deep`): the same
  vectors are reused to flag content-similarity across documents, so
  there's no duplicate infrastructure for search vs. lint.

## Index consistency

The index update is not tied to git at all — it happens synchronously
inside `docs update` / `docs add`, as part of the same operation (the
embedding is the one deferred piece — see Semantic layer — but metadata,
FTS5, and relations are immediate). Git commits are just a
snapshotting/history mechanism on top of files that are already consistent
with the index.

`docs reindex [--changed|--all]` still exists as a manual fallback command,
for cases like a human hand-editing a `.md` file directly, cloning the repo
fresh, or recovering from index corruption — but it's not part of the
normal write flow.

## Status filtering (default visibility)

Closed/resolved documents are not deleted or hidden physically — they stay
in `docs/`, in git history, and remain fully queryable. Visibility is
controlled purely at the read-path/query level:

- `docs context` and `docs query` filter to active statuses by default
  (e.g. exclude `status: resolved`), so a fixed bug does not surface in
  normal agent queries.
- An explicit `--include-resolved` flag (or `docs get <id>`) still returns
  closed documents, e.g. when an agent needs to check whether a similar
  bug was already fixed.
- Optional refinement: instead of a hard exclude, `docs context` can
  down-weight resolved documents in FTS scoring rather than filtering them
  out entirely, if partial relevance turns out to matter in practice.
- For old resolved documents that accumulate over time, `docs archive`
  removes them from active search entirely (see "Archiving vs. deletion"
  below) — a step beyond status filtering, used when volume becomes an
  issue.

## Archiving vs. deletion

Two distinct operations with different reversibility, since an
archive-only policy would let the archive grow unbounded forever:

- **`docs archive <id>`** — soft, reversible. Sets `archived: true` in the
  document's own frontmatter (the file is the source of truth, same as
  `status`) and removes it from active search surfaces (FTS5, embeddings)
  in the index. `docs unarchive <id>` removes the field again. Because the
  flag lives in the file itself, a full `docs reindex --all` from a fresh
  clone correctly skips archived documents from active search without
  needing any separate side-channel state.
- **`docs delete <id>`** — hard, irreversible within the tool itself.
  Deletes the physical file and all its rows (metadata, FTS, embeddings,
  relations). Since git still holds the file's history, this isn't true
  data loss — consistent with the existing "git is the source of truth,
  DB is derived" principle. Used sparingly, e.g. for cleaning up a large
  backlog of long-archived documents.

**Referential integrity on delete:** if other documents have a `related`
link pointing to the id being deleted, `docs delete` fails by default
(Tier 0 style hard check) rather than silently leaving a dangling
reference. An explicit `--force` allows it anyway, in which case the
dangling reference surfaces later as a Tier 1 `docs check` warning rather
than a delete-time error — the agent isn't blocked mid-task, but the
inconsistency isn't silently hidden either.

## Validation strictness tiers

The system borrows the "programming language" metaphor (schema = grammar,
typed `related` links = imports, validation = compiler, graph checks =
linter) but only where it holds: document metadata and the relation graph
are formally checkable, document *body text* is natural language and is
not — so checks are split into three tiers, not one uniform gate. Mixing
these levels (e.g. hard-failing on a text-similarity heuristic) is the main
overengineering risk and is deliberately avoided.

### Tier 0 — hard errors (synchronous, blocks the write)

Runs inline inside every `docs add` / `docs update` call, like a compiler.
Only checks that are cheap and essentially free of false positives:

- Missing required frontmatter field for the document's type
- Invalid `status` value (not in the type's enum)
- Invalid status transition (e.g. `resolved → open` without an explicit
  override flag)
- A `related` id that does not exist in the index
- Malformed frontmatter (not valid YAML, wrong types)

### Tier 1 — structural warnings (async, non-blocking, via `docs check`)

Graph-level issues, run on demand or in CI, never inline in an agent's
write call — an agent mid-task should not be blocked by a "possible
problem":

- Cycles in the relations graph (e.g. `adr-7 supersedes adr-3 supersedes adr-7`)
- Orphan documents (no incoming or outgoing relations) — candidates for
  archiving, analogous to dead code
- Layering violations — a higher-level doc type (e.g. `architecture`)
  depending on a lower-level one (e.g. `issue`), signaling an
  architecture doc too tightly coupled to a transient problem

### Tier 2 — advisory/style (opt-in only, via `docs lint --deep`)

Heuristic, never CI-blocking, run only when a human chooses to:

- Content similarity across documents (DRY at the idea level) via the
  fastembed vectors already computed for `docs context` — surfaced as a
  suggestion, never an error
- Document size/scope creep (SRP violation — one doc covering multiple
  unrelated decisions/issues)

### Why this split

Tier 0 can be as strict as a real compiler because it's fully
deterministic and cheap to verify. Tiers 1–2 deal with things that are
inherently uncertain (graph shape judgment, natural-language meaning), so
they're surfaced as information, not failures — keeping the CLI usable in
an agent's task flow while still giving humans (and periodic audits) a way
to keep the document graph healthy over time.

## CLI commands

| Command | Purpose |
|---|---|
| `docs get <id>` | Return one document in full |
| `docs query --type decision --status open --tag auth` | Structured filtering |
| `docs search "<text>"` | Full-text search |
| `docs context "<agent task>"` | Ranked, minimal relevant document set |
| `docs update <id> --status resolved` | Update a document via CLI (writes file + indexes metadata/FTS/relations synchronously, embedding async) |
| `docs add` | Create a new document with valid frontmatter (writes file + indexes synchronously, embedding async) |
| `docs archive <id>` / `docs unarchive <id>` | Soft-remove/restore a document from active search, reversible |
| `docs delete <id> [--force]` | Hard-delete file + all index rows; blocked by incoming `related` links unless forced |
| `docs tag add <key> --description "..."` / `docs tag list` | Manage the tag registry |
| `docs tag rename <old> <new>` / `docs tag rm <key> [--force]` | Rename a tag across all documents / remove it (blocked while in use unless forced, which strips the key from referencing documents) |
| `docs reindex [--changed\|--all]` | Manual fallback: rebuild index after external/manual file edits |

---

## End-to-end business flow example

**Scenario:** an agent is asked to implement a new authentication endpoint.

1. **Discover context**
   Agent runs `docs context "implement new auth endpoint"`.
   CLI runs FTS scoring on the query, pulls top matches (e.g. `adr-0007`
   "Auth strategy", `issue-12` "Token refresh bug"), then traverses their
   `related` links one hop out (finds `adr-0003` "API versioning policy").
   Returns 3 documents instead of the full `docs/` folder.

2. **Read relevant decisions**
   Agent calls `docs get adr-0007` to read the full accepted decision on
   auth strategy before writing code, ensuring the implementation follows
   the agreed approach.

3. **Implement the feature**
   Agent writes the endpoint code (outside the doc system).

4. **Record a new decision or open issue**
   If the implementation surfaces a new tradeoff, agent runs:
   `docs add --type decision --title "Refresh token rotation" --description "..." --tags auth,api --related adr-0007`
   (`auth` and `api` must already exist in the tag registry, or the call
   fails Tier 0 validation.) CLI generates a new `adr-00xx` file with valid
   frontmatter, agent fills in the body.

5. **Update status of resolved issue**
   Agent runs `docs update issue-12 --status resolved`.
   CLI validates the transition, rewrites frontmatter in `issues/issue-12.md`,
   and updates its metadata/FTS rows synchronously — the index is current
   immediately (a status-only change doesn't touch the embedding).

6. **Commit**
   Agent (or human) commits the changed `.md` files to git, purely as a
   history/snapshot action. The index was already updated during steps 4–5
   and does not depend on this commit happening.

7. **Human review**
   A teammate reviews the diff in the PR as plain markdown — no DB
   inspection required — and can trace the decision's history via
   `git log` on the file.
