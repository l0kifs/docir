---
created: '2026-08-15'
description: The command vocabulary agents drive docir with, the static site build,
  and a worked flow through them end to end.
id: arch-7fd54a82f7d6
related:
- kind: refines
  to: arch-1cfb1b212237
status: active
tags:
- architecture
title: Doc-Index CLI — the CLI surface
type: architecture
updated: '2026-08-16'
---

## CLI commands

Every command below exists in `docir --help`; the groups are `agent`, `daemon`,
`mcp`, `schema`, `self` and `tag`. Global flags come *before* the command
(`docir --pretty get <id>`): `--home`, `--store`, `--no-daemon`, `--json`,
`--pretty`, `--no-trim`.

**Read** — `query`/`search`/`context` return skeletons (no body); only `get` returns one.

| Command | Purpose |
|---|---|
| `docir get <id> [--section "<heading>"]` | One document in full, or just the span under one heading |
| `docir query --type decision --status accepted --tag auth` | Structured filtering; also `--owner`, `--stale`, `--code`, `--limit/--offset` |
| `docir search "<text>"` | Full-text over title, description and body |
| `docir context "<agent task>"` | Ranked minimal set (FTS5 + semantic, fused) plus graph neighbours; `--expand`, `--min-score` |

**Write** — the single sanctioned path to a markdown file.

| Command | Purpose |
|---|---|
| `docir add --type <t> --title "..." --description "..."` | Create a document with valid frontmatter; id allocated for you |
| `docir update <id> --status resolved` | Metadata patch and/or a body edit (`--append-section`, `--replace-section`, `--replace-body --force`) |
| `docir archive <id>` / `docir unarchive <id>` | Soft-remove/restore from active search, reversible |
| `docir delete <id> [--force]` | Hard-delete file + index rows; blocked by incoming `related` links unless forced, which unlinks them |
| `docir tag add <key> --description "..."` / `docir tag list` | Manage the tag registry |
| `docir tag rename <old> <new>` / `docir tag rm <key> [--force]` | Rename across every referencing document / remove it |

**Maintenance** — the derived index and the corpus's shape.

| Command | Purpose |
|---|---|
| `docir reindex [--changed]` | Rebuild the index from the canonical files; re-embeds what it re-saves; read `documents_skipped` |
| `docir check [--strict] [--strict-all] [--fix]` | Tier 1 structural findings; `--strict` is the CI gate (errors only), `--fix` repairs what needs no guess |
| `docir lint --deep` | Tier 2 advisories (content similarity, scope creep) |
| `docir embed --flush` | Force a synchronous recompute of dirty vectors |
| `docir schema show` / `docir schema validate` | Inspect the merged schema / check `docs-schema.yaml` before a write reaches it |

**Bootstrap, serving and the installation itself.**

| Command | Purpose |
|---|---|
| `docir init [DIR] [--profiles ...]` | Create a project-local `.docir` store that commands discover by walking up |
| `docir build --out site/` | Render the corpus as a self-contained static site |
| `docir agent install` / `docir agent update` | Install or refresh AI-assistant instruction files |
| `docir daemon start` / `status` / `stop` | Escape hatches; the daemon is otherwise spawned and reaped for you |
| `docir mcp serve` | Expose the same vocabulary as MCP tools over the same dispatcher |
| `docir self status` / `docir self upgrade` | What is installed and whether it is current / upgrade and resync the store |
| `docir version` | Print the docir version |

---|---|
| `docir get <id>` | Return one document in full |
| `docir query --type decision --status accepted --tag auth` | Structured filtering |
| `docir search "<text>"` | Full-text search |
| `docir context "<agent task>"` | Ranked, minimal relevant document set |
| `docir update <id> --status resolved` | Update a document via CLI (writes file + indexes metadata/FTS/relations synchronously, embedding async) |
| `docir add` | Create a new document with valid frontmatter (writes file + indexes synchronously, embedding async) |
| `docir archive <id>` / `docir unarchive <id>` | Soft-remove/restore a document from active search, reversible |
| `docir delete <id> [--force]` | Hard-delete file + all index rows; blocked by incoming `related` links unless forced |
| `docir tag add <key> --description "..."` / `docir tag list` | Manage the tag registry |
| `docir tag rename <old> <new>` / `docir tag rm <key> [--force]` | Rename a tag across all documents / remove it (blocked while in use unless forced, which strips the key from referencing documents) |
| `docir reindex [--changed]` | Manual fallback: rebuild index after external/manual file edits |

---

## Publishing the corpus

`docir build --out site/` renders the whole store as a self-contained static
site — one HTML page per document plus an index, no external requests, so it
works from `file://` and publishes to GitHub Pages or S3 unchanged. It is what
turns the corpus into something reviewable by people who will never run the CLI.

The site is derived like the index, and is guarded accordingly: every `*.html`
in `--out` is removed before writing, so a document deleted from the store
cannot survive as an orphaned page nobody can reach and nobody knows is stale.
"Delete everything here first" has to be sure it owns "here" — a previous docir
build is recognised, and any other non-empty directory is refused unless
`--force`, because `--out` is a path a person types.

The build does one `query` and then one `get` per document. Bodies are absent
from every list path by contract, so a build that stopped at `query` would
report the right document count and publish empty pages — which looks exactly
like success.

Architecturally, `publishing` is a **leaf module**: it takes documents as data
(the `docir get` JSON shape) rather than importing `documents.api`. The site is
a projection of the public contract, not a second reader of the aggregate — do
not "simplify" it by handing it a `DocumentService`.

## End-to-end business flow example

**Scenario:** an agent is asked to implement a new authentication endpoint.

1. **Discover context**
   Agent runs `docir context "implement new auth endpoint"`. The CLI ranks the
   corpus twice — FTS5 over the text and cosine over the vectors, per document
   *and* per section — fuses the two rankings, then expands one hop across the
   relation graph inside the same `--limit` budget. Expansion follows outgoing
   edges **and** incoming successor edges, so a decision that supersedes a hit
   arrives with it rather than sitting one hop away backwards.
   It returns a handful of documents instead of the whole store — as
   **skeletons**: frontmatter, typed edges, staleness, and no bodies. That is
   the contract that makes the step cheap.

2. **Read only what matters**
   Agent judges relevance from the skeletons — by `similarity`, the raw cosine,
   never by `score`, which is rank-derived and says nothing about how good a
   match was — then calls `docir get adr-3f9a2b1c7d4e` for the bodies it
   actually needs. If the hit named a `matched_section`, that heading goes
   straight to `docir get <id> --section "<heading>"` and the agent pays for one
   section instead of a body ten times its size.

3. **Check what the change is governed by**
   `docir query --code src/auth/login.py` answers the other direction: which
   documents declared they govern the files about to change. The patterns are
   matched as text, so a file the branch *deletes* still finds its decisions.

4. **Implement the feature** (outside the doc system).

5. **Record a new decision or open issue**
   If the implementation surfaces a new tradeoff:
   `docir add --type decision --title "Refresh token rotation" --description "..." --tags auth,api --related adr-3f9a2b1c7d4e --code "src/auth/**"`
   `auth` and `api` must already exist in the tag registry and the `--related`
   target must exist, or the call fails Tier 0. The CLI allocates the id from
   the index counter — never by scanning files, which is what keeps parallel
   agents from minting the same one — writes the file with valid frontmatter,
   and indexes it. The vector is queued, not computed: add `--wait-embeddings`
   if the next command must find it semantically.

6. **Update the status of the resolved issue**
   `docir update issue-7d1e4b9c02fa --status resolved`. The CLI validates the
   transition against the type's state machine, rewrites the frontmatter, and
   updates metadata, FTS and relations synchronously — the index is current when
   the command returns. A status-only change does not touch the embedding.

7. **Commit**
   Agent or human commits the changed `.md` files, purely as a history action.
   The index was already updated in steps 5–6 and does not depend on the commit;
   it is gitignored, and a fresh clone rebuilds it with `docir reindex`.

8. **Human review**
   A teammate reviews the diff as plain markdown — no database inspection — and
   traces the decision's history with `git log` on the file. For a reader who
   will not run the CLI, `docir build --out site/` renders the same corpus as a
   browsable site with the relation graph in both directions.
