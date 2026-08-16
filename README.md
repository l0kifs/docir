<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/l0kifs/docir/main/assets/logo/docir-lockup-dark.png" />
  <img src="https://raw.githubusercontent.com/l0kifs/docir/main/assets/logo/docir-lockup.png" alt="docir" width="260" />
</picture>

**doc**uments as **IR** — a CLI that *compiles* git-backed markdown<br />into a verifiable, read-optimized index for AI coding agents.

[![PyPI](https://img.shields.io/pypi/v/docir)](https://pypi.org/project/docir/) [![Python](https://img.shields.io/pypi/pyversions/docir)](https://pypi.org/project/docir/) [![CI](https://img.shields.io/github/actions/workflow/status/l0kifs/docir/ci.yml?branch=main)](https://github.com/l0kifs/docir/actions) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[Quickstart](#quickstart) · [Why not just…](#why-not-just) · [The model](#the-model) · [Commands](#commands) · [Going further](#going-further) · [Live site](https://l0kifs.github.io/docir/index.html)

<br />

<img src="https://raw.githubusercontent.com/l0kifs/docir/main/assets/docir-demo.svg" alt="A terminal: docir context returns three ranked documents with no bodies, each naming the section that matched; docir get --section then returns just that section." width="820" />

<sub>Ask in your own words. Get ranked skeletons — no bodies, so scanning is cheap.<br />Read the one section that matched.</sub>

</div>

---

## The idea

"IR" is *intermediate representation* — the thing a compiler turns source code into.
docir treats your markdown the same way: the **files are the source**, and the SQLite
index (metadata + FTS5 full-text + a typed relation graph + semantic embeddings) is a
**derived artifact you can throw away and rebuild**.

```text
  source of truth     docir                  derived index
  canonical           the compiler           rebuildable · gitignored
  ───────────────     ──────────────────     ─────────────────────────
  decisions/*.md      parse · validate       metadata · FTS5
  issues/*.md     ──▶ allocate ids       ──▶ relation graph (typed)
  tags.yaml           embed (deferred)       vector embeddings
```

> **Git is canonical.** `docir reindex` rebuilds the entire index from the files. When the
> database and the files disagree, the files win.

## Quickstart

```bash
# 1. install  (~240 MB of deps; a 64 MB embedding model downloads on first use, once —
#              the only step that needs network. DOCIR_EMBEDDER=deterministic opts out.)
uv tool install docir          # or: pipx install docir

# 2. scope docs to this repo (creates ./.docir, like `git init`)
#    skip it and docs go to the global ~/.docir — docir warns if you are in a repo
docir init

# 3. teach this repo's AI agent to drive docir (writes a Claude Code skill)
docir agent install            # --agent claude-writing adds the doc-writing rules;
                               # --agent agents links the skills from AGENTS.md

# 4. capture a decision…
docir add --type decision --title "Auth strategy" \
    --description "How the service authenticates API clients." --stdin < draft.md

# 5. …and retrieve it by intent, next session
docir context "implement a new auth endpoint"
```

In a terminal, `docir context` prints ranked, body-less **skeletons** — frontmatter and
typed edges, no body — so you scan wide, then fetch a body by id with `docir get`:

```console
$ docir context "implement a new auth endpoint"
┏━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ id         ┃ type     ┃ status   ┃ title              ┃ description                      ┃ score ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ adr-0001   │ decision │ proposed │ Auth strategy      │ How the service authenticates    │ 0.033 │
│            │          │          │                    │ API clients.                     │       │
│ issue-0001 │ issue    │ open     │ Token refresh race │ Refresh token race under         │ 0.016 │
│            │          │          │                    │ concurrent logins.               │       │
└────────────┴──────────┴──────────┴────────────────────┴──────────────────────────────────┴───────┘
```

Built for agents, though: when the output is **captured** (stdout isn't a TTY), the same
command emits **compact, trimmed JSON** — no borders, empty fields dropped, ~40% fewer tokens:

```console
$ docir context "implement a new auth endpoint" | cat
[{"id":"adr-0001","title":"Auth strategy","description":"How the service authenticates API clients.","type":"decision","status":"proposed","tags":["auth"],"archived":false,"stale":false,"score":0.0328,"similarity":0.8951,"via_graph":false}, ...]
```

*An absent field means its default (no owner, not stale). `score` fuses the full-text and
vector rankings, so ordering is the point and the absolute value means little.
`similarity` is the raw cosine against your query and does carry absolute meaning — it is
what `--min-score` filters on, which is what makes an empty result a real answer.*

## Why not just…

| | plain `.md` files | RAG over your docs | **docir** |
|---|:---:|:---:|:---:|
| Consistent frontmatter / schema | ❌ | ❌ | ✅ enforced |
| Retrieval by meaning | ❌ | ✅ | ✅ lexical + semantic † |
| Typed relation graph | ❌ | ❌ | ✅ |
| Knows what's stale | ❌ | ❌ | ✅ |
| Works offline, nothing to run | ✅ | ⚠️ | ✅ after the model downloads once † |
| Token-cheap for agents | ❌ | ⚠️ | ✅ skeletons |

*Orientation, not a shoot-out — the right tool depends on your setup.*

† Semantic search runs a quantized, CPU-only model locally — nothing is sent anywhere,
but it is ~240 MB of dependencies and a 64 MB download. `DOCIR_EMBEDDER=deterministic`
opts out, at a measured cost to recall:
[what the model costs and what the fallback loses](https://l0kifs.github.io/docir/ref-e7534f1c812d.html).

## The model

- **One write path.** Agents never edit markdown directly; every write goes through the
  CLI, which guarantees frontmatter/schema consistency and collision-free id allocation.
  You are not an agent: the files are yours, and the rule for humans is narrower — see
  [what you may edit by hand](#what-you-may-edit-by-hand).
- **Reads return skeletons.** `query` / `search` / `context` return frontmatter + typed
  edges + staleness — *no body*. Fetch bodies by id with `get`, or a single section with
  `get --section`. An agent scans wide cheaply, then reads deep only where it matters.
- **Staleness is data, not a guess.** Optional `owner` / `verified` fields plus a per-type
  review cadence make "is this doc still true?" a first-class, checkable fact — and a
  worklist: `docir query --owner platform-team --stale` is one steward's review queue,
  cleared a document at a time with `docir update <id> --verified`.
- **Relations are typed.** A `related` edge carries a *kind* (`supersedes`, `depends_on`,
  `implements`, …) — a real graph, not a bag of links.
- **A document can name the code it governs.** Optional `code` globs
  (`docir add --code "src/auth/**"`) record which files a decision is about, and
  `docir query --code src/auth/login.py` asks it in reverse: which decisions govern the
  file I am editing. At review time,
  `docir query --code $(git diff --name-only origin/main...HEAD)` lists what a branch
  should be read against — a notice, not a gate.
- **A decision that can be enforced is enforced by a test.** Point `code` at the test that
  fails when the code contradicts the decision, and CI already enforces it — in your
  language, with your fixtures. docir ships no rule engine; it records the link and warns
  when that test disappears.
- **Only embeddings are deferred.** A content change flags the vector dirty and returns;
  the file, metadata, full-text index and relations are all current when the command
  returns. Force a flush with `--wait-embeddings`, `docir embed --flush`, or
  `docir reindex --embeddings`.

## What you may edit by hand

The files are git-backed markdown and `docir reindex` exists precisely to pick up an
outside change — so hand-editing is supported, but not on every field:

| | by hand | instead |
|---|---|---|
| document **body** | ✅ | — |
| `docs-schema.yaml`, `docs/tags.yaml` | ✅ | no CLI write path for the schema |
| `tags`, `status`, `related` | ❌ | `docir update --set-tags / --status / --set-related` |
| `type` | ❌ | `docir update <id> --type <new>` — the id stays, the file moves |
| `code` | ❌ | `docir update <id> --set-code "src/auth/**"` |
| `id` | ❌ never | it is the primary key; changing it orphans every inbound link |
| `verified` | ❌ never | `docir update <id> --verified` — it asserts a human re-read the doc |

**Then run `docir reindex && docir check`** — or let the daemon do the reindex for you.
It watches `.docir/docs/` and rebuilds what changed within a second of the edit, which
is safe precisely because the files are canonical: a reindex only makes the index agree
with them, and writes no markdown. `DOCIR_WATCH=0` turns it off; `--no-daemon` runs
never watch, so CI still needs the explicit command. A hand-written `verified` date is
the one thing nothing can verify, which is exactly why it should not be written by hand.

## Commands

| Command | What it does |
|---|---|
| `docir init` | Scope docs to a project-local `./.docir` store (like `git init`) |
| `docir add` | Create a document — the single write path |
| `docir update` | Edit content, metadata, or relations of an existing document |
| `docir context <query>` | Ranked relevant set (skeletons) — full-text + vector, fused (`--min-score` to filter noise) |
| `docir search` / `query` | Full-text search (title/description/body — **not tags**) / structured filter. Both page with `--limit`/`--offset`; `query --owner X --stale` is a review queue, `query --code <path>` the decisions governing a file |
| `docir get <id>` | Full document with body — or one section with `--section "<heading>"` |
| `docir check` | Structural findings — duplicate ids, dangling edges, staleness (`--strict` gates CI on errors, `--fix` repairs them) |
| `docir agent install` | Teach this repo's AI agent to drive docir |
| `docir self upgrade` | Upgrade docir, then resync this store: reindex, refresh the agent files, report what `check` finds |
| `docir build --out site/` | Render the store as a self-contained static site for humans |
| `docir mcp serve` | Serve the same commands as MCP tools, for a client that speaks MCP |

### Full command reference

```
init · add · update · archive · unarchive · delete
get · query · search · context · build
tag {add, list, rename, rm}
agent {install, update}
schema {show, validate}
self {status, upgrade}
check [--fix] · lint · reindex · embed · version
daemon serve · mcp serve
```

**Where state lives.** Store precedence (highest first): `--home` → `DOCIR_HOME` → a
project-local `.docir/` found by walking up from the CWD → the global `~/.docir`.
`docir init` keeps docs with the code: `.docir/docs/` and `docs-schema.yaml` are
**committed**, the derived index is **gitignored**. The daemon keeps the embedding model
warm and serializes writes; `--no-daemon` runs any command in-process instead.

**Output.** A Rich table at a TTY, compact JSON when piped; `--json` / `--pretty` force
either, `--no-trim` keeps every field. That applies to `--help` too — `docir --help | cat`
returns the command vocabulary as JSON, so an agent can discover the CLI without parsing
box-drawing characters.

**Two limits worth knowing up front.** Search covers title, description and body but
**not tags** — tags are a controlled vocabulary for `docir query --tag`, kept out of the
full-text index so one tag match cannot flood out the text matches. And `context` is not
paged: it returns a relevance-ranked set bounded by `--limit`, a token budget rather than
a browse path.

**Publishing.** `docir build --out site/` renders the store as a self-contained static
site for the people who approve decisions. `--title` names it — without it every page
reads "Documentation"; `--logo` sets the mark and the favicon; `--mermaid
vendor/mermaid.min.js` draws fenced diagrams; `--include-archived` publishes archived
documents; `--force` lets it overwrite a directory docir did not build. Flags, CI and the
rest are in [the runbook](https://l0kifs.github.io/docir/run-6ab65e277573.html).

## Two ways an agent reaches docir

Some agents run shell commands; some only call MCP tools. Both get the same vocabulary,
because both go through the same dispatcher — an MCP tool and its CLI command cannot
answer differently.

```bash
docir agent install                       # a Claude skill (AGENTS.md links it): drive the CLI
claude mcp add docir -- docir mcp serve   # or the same commands as MCP tools
```

`docir mcp serve` speaks stdio (what an MCP client spawns) or `--transport http`, and
needs no extra — the MCP server ships with docir, because an agent that only speaks MCP
cannot install the extra it would need to reach docir in the first place. `uvx docir mcp
serve` runs it without installing anything. The tools are named `docir_context`,
`docir_get`, `docir_add`, … and return the same body-less skeletons the CLI does.

## Schema: core + profiles

Documents are constrained by a per-type schema (required fields, status grammar, allowed
relations). docir ships a frozen, domain-agnostic **core** plus swappable **profiles** —
`software` (default: `decision` / `issue` / `architecture` / `release_note`), `research`,
`ops`, `qa`, `legal`. A `docs-schema.yaml` merges `core → profiles → inline`, so you
extend it without mutating the base.

```bash
docir init --profiles software,qa   # pick profiles up front
docir init --id-style sequential    # readable adr-0007 instead of the default random
docir schema show                   # the merged result — what validation enforces
docir schema validate               # check an edit before it reaches a write
```

Ids are random by default (`adr-3f9a2b1c7d4e`), which two branches can never mint
identically. `--id-style sequential` trades that for human-friendly `adr-0007` numbering,
collision-free within one store — a merge can bring two branches that allocated the same
number, and `docir check` reports it as `duplicate-id`.

### Renaming a type

Merging only adds types, so `disable_types:` is how you give one up — and it is what frees
that type's `prefix` for your own to claim, which is what lets a renamed corpus keep the
ids it already has. Documents are then moved over one at a time; nothing is retyped for
you, because only you know what each old status becomes.

```yaml
# docs-schema.yaml
profiles: [software]
disable_types: [decision]        # the name stops resolving, and `adr` is free
types:
  product_decision:
    prefix: adr                  # the corpus keeps every adr-... id it has
    default_status: draft
    statuses: {draft: [active], active: []}
```

```bash
docir schema validate
docir query --type decision --limit 500 | jq -r '.[].id' \
  | xargs -I{} docir update {} --type product_decision --status active
docir reindex && docir check
```

Between the schema edit and the loop, `docir check` reports the not-yet-moved documents as
`unknown-type` — a warning, so nothing is blocked. Retyping a document never changes its
id: `adr-3f9a2b1c7d4e` stays itself under any type, because it is the only address every
`related` edge has for it.

## Upgrading

The schema, the agent instructions and the site templates ship *inside the package*, so a
release can change what a store enforces and what an agent reads with nothing in your
`git diff` to review. Migrations, a daemon serving old code and vectors from a superseded
model all sort themselves out on the next command. What is left is one command:

```bash
docir self upgrade        # install the new docir, then resync this store
docir self status         # what is installed, and whether anything newer exists
```

Where docir does *not* own its environment — a checkout, a project whose lockfile pins it,
an ephemeral `uvx` run — it says so and resyncs the store anyway. The full procedure is
[a runbook in docir's own store](https://l0kifs.github.io/docir/run-f4a756206fe0.html).

## Going further

docir keeps its own documentation *in docir* and publishes it with `docir build`, so the
depth lives where an agent can retrieve it rather than in this file:

| | |
|---|---|
| [Publish the store as a static site](https://l0kifs.github.io/docir/run-6ab65e277573.html) | `docir build` for the people who approve decisions — flags, CI, the `--out` guard, mermaid diagrams |
| [Read across repositories](https://l0kifs.github.io/docir/run-45b267a709b4.html) | Federated reads over peers declared in `.docir/stores.yaml` — and why writes never federate |
| [The embedding model](https://l0kifs.github.io/docir/ref-e7534f1c812d.html) | What it costs, what the fallback loses, why every section is embedded separately |
| [Upgrade docir in a project](https://l0kifs.github.io/docir/run-f4a756206fe0.html) | `docir self upgrade`, schema drift, and what resyncs itself |
| [Every ADR and architecture note](https://l0kifs.github.io/docir/index.html) | The design rationale as documents — or `docir query --type decision` |

## Architecture

Vertical bounded-context **modules** (`documents`, `tags`, `indexing`, `agents`,
`publishing`, `release`) over a shared **platform**, wired by thin **entry_points**.
Dependencies flow `entry_points → modules → platform → config`; boundaries are enforced
by [tach](https://docs.gauge.sh) in CI — not by convention. Each module exposes exactly
one public file (`api.py`) described by a `CONTRACT.md`.

The design rationale and the module rules are themselves docir documents — run
`docir get arch-1cfb1b212237` and `docir get arch-322e5f992ad2`, or browse
[`.docir/docs/architectures/`](.docir/docs/architectures/). [`docs/README.md`](docs/README.md)
maps every pre-migration path to its id.

## Contributing

Issues and PRs welcome. docir dogfoods itself: its ADRs, architecture documents, runbooks
and gap register live in its own store, so `docir context "what you are about to change"`
is how you orient. Read the architecture rules and the ADRs (`docir query --type decision`)
first — module boundaries are machine-checked by [tach](https://docs.gauge.sh) in CI,
alongside lint, type-check, and a coverage gate. Every design deviation is recorded as an
ADR, added with `docir add --type decision`, never by hand.

```bash
uv sync                                              # dev environment
uv run python benchmarks/run.py                      # retrieval quality + token cost
uv run python benchmarks/latency.py                  # read latency by corpus size + daemon mode
uv run python benchmarks/tokens.py                   # token cost by corpus size, vs a grep baseline
uv run pytest --cov=docir --cov-fail-under=90        # tests + coverage gate
uv run ruff check . && uv run ty check && uv run tach check
```

## License

MIT © Sergei Konovalov
