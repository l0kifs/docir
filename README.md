<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/l0kifs/docir/main/assets/logo/docir-lockup-dark.png" />
  <img src="https://raw.githubusercontent.com/l0kifs/docir/main/assets/logo/docir-lockup.png" alt="docir" width="260" />
</picture>

**doc**uments as **IR** — a CLI that *compiles* git-backed markdown<br />into a verifiable, read-optimized index for AI coding agents.

[![PyPI](https://img.shields.io/pypi/v/docir)](https://pypi.org/project/docir/) [![Python](https://img.shields.io/pypi/pyversions/docir)](https://pypi.org/project/docir/) [![CI](https://img.shields.io/github/actions/workflow/status/l0kifs/docir/ci.yml?branch=main)](https://github.com/l0kifs/docir/actions) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[The idea](#the-idea) · [Quickstart](#quickstart) · [Why not just…](#why-not-just) · [The model](#the-model) · [Editing by hand](#what-you-may-edit-by-hand) · [Commands](#commands) · [Conventions](#conventions)<br />
[Reaching docir](#two-ways-an-agent-reaches-docir) · [Schema](#schema-core--profiles) · [Upgrading](#upgrading) · [Going further](#going-further) · [Architecture](#architecture) · [Support](#support) · [Contributing](#contributing) · [License](#license) · [Live site](https://l0kifs.github.io/docir/index.html)

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

**Requirements.** Python 3.12+ and [uv](https://docs.astral.sh/uv/) (or pipx). Linux, macOS
or Windows — everything runs locally, and only the first-run model download needs network.

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
typed edges, no body — so you scan wide, then fetch the bodies by id with one `docir get`. Built
for agents, though: when the output is **captured** (stdout isn't a TTY), the same command
emits **compact, trimmed JSON** — no borders, empty fields dropped, ~40% fewer tokens:

```console
$ docir context "implement a new auth endpoint" | cat
[{"id":"adr-0001","title":"Auth strategy","description":"How the service authenticates API clients.","type":"decision","status":"proposed","tags":["auth"],"archived":false,"stale":false,"score":0.0328,"similarity":0.8951,"via_graph":false}, ...]
```

An absent field means its default (no owner, not stale). `score` orders the results and
means little on its own; `similarity` is the raw cosine against your query, and is what
`--min-score` filters on — which is what makes an empty result a real answer. Both numbers
are explained in [how to read a ranked result](https://l0kifs.github.io/docir/ref-0e14d7c32dbf.html).

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
  cleared a document at a time with `docir update <id> --verified`. Un-stamped documents age from
  `created`, never from the last edit, so writing into one cannot quietly take it off the
  queue. And a stamp does not outlive what it covered: edit a verified document's title,
  description or body and the verification is withdrawn, the cadence restarting from that day —
  pass `--verified` with the edit if you re-read it. `--clear-verified` takes back a stamp that
  asserts a review nobody did, and grants no window at all: that document ages from `created`
  again. A verification also fingerprints what it covered, so `docir check` flags one that
  outlived a hand-edit.
- **Relations are typed.** A `related` edge carries a *kind* (`supersedes`, `depends_on`,
  `implements`, …) — a real graph, not a bag of links. `docir check` warns about a document
  with no edge at all (`orphan`), and only an edge closes it — naming an id in a paragraph
  does not, or the triage of the orphan list would empty the list. A document that is meant
  to stand alone says so instead:
  `docir update <id> --set-isolated "scope deferred; nothing depends on it yet"`, audited
  later with `docir query --expr "isolated"`.
- **A document can name the code it governs.** Optional `code` globs
  (`docir add --code "src/auth/**"`) record which files a decision is about, and
  `docir query --code src/auth/login.py` asks it in reverse: which decisions govern the
  file I am editing. At review time,
  `docir query --code $(git diff --name-only origin/main...HEAD)` lists what a branch
  should be read against — a notice, not a gate. Point `code` at the *test* that fails
  when the code contradicts the decision and CI already enforces it, in your language
  with your fixtures: docir ships no rule engine, it records the link and warns when
  that test disappears.
- **Only embeddings are deferred.** A content change flags the vector dirty and returns;
  the file, metadata, full-text index and relations are all current when the command
  returns. Force a flush with `--wait-embeddings`, `docir embed --flush`, or a full
  `docir reindex`, which re-embeds every document it re-saves and reports how many.

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
| `verified` | ❌ never | `docir update <id> --verified` — it asserts somebody re-read the doc |
| `revoked` | ❌ never | Set by editing a verified doc; the cadence runs from it |
| `verified_content` | ❌ never | The digest `docir check` compares the reviewed text against |
| `isolated` | ❌ never | `docir update <id> --set-isolated "<why>"` — it exempts the doc from `orphan` |

**Then run `docir reindex && docir check`** — or let the daemon do the reindex for you.
It watches `.docir/docs/` and rebuilds what changed within a second of the edit, which
is safe precisely because the files are canonical: a reindex only makes the index agree
with them, and writes no markdown. `DOCIR_WATCH=0` turns it off; `--no-daemon` runs
never watch, so CI still needs the explicit command.

## Commands

| Command | What it does |
|---|---|
| `docir init` | Scope docs to a project-local `./.docir` store (like `git init`) |
| `docir add` | Create a document — the single write path |
| `docir update` | Edit content, metadata, or relations of an existing document |
| `docir context <query>` | Ranked relevant set (skeletons) — full-text + vector, fused (`--also` to add a phrasing you could defend, `--min-score` to filter noise, `--explain` for the trace) |
| `docir search` / `query` | Full-text search (title/description/body — **not tags**) / structured filter. Both page with `--limit`/`--offset`; `query --owner X --stale` is a review queue, `query --code <path>` the decisions governing a file, `query --expr` a JMESPath question over fields and resolved edges |
| `docir get <id> [<id>...]` | Full documents with bodies — several in one command, and `<id>#<heading>` for just one section of one |
| `docir check` | Structural findings — duplicate ids, dangling edges, staleness (`--strict` gates CI on errors, `--fix` repairs them) |
| `docir doctor` | Diagnose the *environment* — the installation, this store's index, the embedding model, the daemon, the peers (`--strict` gates a setup step on errors) |
| `docir agent install` | Teach this repo's AI agent to drive docir |
| `docir self upgrade` | Upgrade docir, then resync this store: reindex, refresh the agent files, report what `check` finds |
| `docir bench fixture.yaml` | Score this store's retrieval against tasks whose answers you know |
| `docir build --out site/` | Render the store as a self-contained static site for humans |
| `docir mcp serve` | Serve the same commands as MCP tools, for a client that speaks MCP |

### Full command reference

```
init · add · update · archive · unarchive · delete
get · query · search · context · build · bench
tag {add, list, rename, rm}
agent {install, update}
schema {show, validate}
self {status, upgrade}
check [--fix] · lint · reindex · embed · version
daemon serve · mcp serve
```

**Reading in bulk.** `docir get` takes as many ids as you like, and `<id>#<heading>` addresses
one section of one — `docir get adr-3f9a2b1c7d4e "arch-0002#Decision"`. This is worth doing
every time: a docir read is dominated by starting the process, not by retrieval, so five
separate calls cost roughly five times one. With two or more ids the reply becomes
`{"documents": [...], "missing": [...]}`; an id that no longer exists is reported in `missing`
rather than failing the read.

**Editing a body.** Bodies are edited one section at a time — `--append-section`,
`--replace-section` and `--remove-section` all take a heading — with `--replace-body --force`
reserved for a wholesale rewrite. The two writing modes emit the `##` line themselves, so
`--body` is the prose beneath it and nothing more; handing one a section exactly as
`docir get --section` printed it errors rather than doubling its heading.

**Publishing.** `docir build --out site/` renders the store as a self-contained static site.
`--title` names it (without it every page reads "Documentation"), `--logo` sets the mark and
favicon, `--mermaid mermaid.min.js` draws fenced diagrams (the classic-script bundle, which sets
`window.mermaid`: fetch `https://cdn.jsdelivr.net/npm/mermaid@11.16.1/dist/mermaid.min.js` —
the `.mjs` module entry is refused), `--include-archived` adds
archived documents, `--force` overwrites a directory docir did not build.

## Conventions

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

## Two ways an agent reaches docir

Some agents run shell commands; some only call MCP tools. Both get the same vocabulary,
because both go through the same dispatcher — an MCP tool and its CLI command cannot
answer differently.

```bash
docir agent install                       # a Claude skill (AGENTS.md links it): drive the CLI
claude mcp add docir -- docir mcp serve   # or the same commands as MCP tools
```

The MCP server ships inside docir — an agent that only speaks MCP could not install an
extra to reach it. The tools are named `docir_context`, `docir_get`, `docir_add`, … and
return the same body-less skeletons the CLI does. Transports, the writing skill and which
path to choose are in
[Connect an agent to docir](https://l0kifs.github.io/docir/run-00b9e9f30914.html).

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

`schema validate` answers two things: whether the file loads, and what it costs the
corpus — how many documents carry a type, status, required field or relation kind this
schema no longer accepts. It reads the files rather than the index, so it works on a
fresh clone, and it never changes the exit code: the schema is valid, and the documents
are what moved.

**Not writing in English?** The default embedding model, `bge-small-en-v1.5`, is
English-only, so a corpus in another language ranks no better than full-text search.
Name another with a top-level `embed_model:` key — measured alternatives are
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 dim, 220 MB, the
drop-in) and `…-mpnet-base-v2` (768 dim, 1.0 GB). Any other model
[fastembed](https://github.com/qdrant/fastembed) supports is accepted with one warning:
docir embeds queries and documents through the same call, so a model trained on
asymmetric `query:` / `passage:` prefixes ranks below its published numbers. It lives in
the schema rather than an environment variable because the index is gitignored — two
clones holding different models would each re-embed the corpus behind the other. Changing
it re-embeds on the next write or `docir embed --flush`; vectors record which model made
them, so nothing is ever compared across models. `docir self status` reports the one in
force.

Ids are random by default (`adr-3f9a2b1c7d4e`), which two branches can never mint
identically. `--id-style sequential` trades that for human-friendly `adr-0007` numbering,
collision-free within one store — a merge can bring two branches that allocated the same
number, and `docir check` reports it as `duplicate-id`.

Merging only adds types, so `disable_types:` is how you give one up — and it is what frees
that type's `prefix` for your own to claim, which is what lets a renamed corpus keep the ids
it already has. Retyping never re-mints an id, because it is the only address every `related`
edge has for the document. The schema edit, the migration loop and what `docir check` reports
in between are in
[Rename a document type](https://l0kifs.github.io/docir/run-781485012ad0.html).

## Upgrading

The schema, the agent instructions and the site templates ship *inside the package*, so a
release can change what a store enforces and what an agent reads with nothing in your
`git diff` to review. Migrations, a daemon serving old code and vectors from a superseded
model all sort themselves out on the next command. What is left is one command:

```bash
docir self upgrade        # install the new docir, then resync this store
docir self status         # what is installed, and whether anything newer exists
```

When they do not — or when a read simply contradicts what you can see in the files —
`docir doctor` is the one command that reports every way docir can be *subtly* wrong: a
daemon still serving code you replaced, a `DOCIR_EMBEDDER` left over from a test run, an
index built by another version or behind the files it projects, a schema that moved under the
corpus, a peer store every read is silently skipping, writes about to land in `~/.docir`
because nobody ran `docir init` here. Each finding names the command that closes it, and
`--strict` exits nonzero on the ones that mean docir cannot work at all. It makes no network
call and loads no model unless you pass `--probe`.

Where docir does *not* own its environment — a checkout, a project whose lockfile pins it,
an ephemeral `uvx` run — it says so and resyncs the store anyway. The full procedure is
[a runbook in docir's own store](https://l0kifs.github.io/docir/run-f4a756206fe0.html).

## Going further

docir keeps its own documentation *in docir* and publishes it with `docir build`, so the
depth lives where an agent can retrieve it rather than in this file:

| | |
|---|---|
| [Publish the store as a static site](https://l0kifs.github.io/docir/run-6ab65e277573.html) | `docir build` for the people who approve decisions — flags, CI, the `--out` guard, mermaid diagrams |
| [Read across repositories](https://l0kifs.github.io/docir/run-45b267a709b4.html) | Federated reads over peers declared in `.docir/stores.yaml` — every hit labelled with the corpus that answered it, and why writes never federate |
| [The embedding model](https://l0kifs.github.io/docir/ref-e7534f1c812d.html) | What it costs, what the fallback loses, why every section is embedded separately |
| [Upgrade docir in a project](https://l0kifs.github.io/docir/run-f4a756206fe0.html) | `docir self upgrade`, schema drift, and what resyncs itself |
| [Rename a document type](https://l0kifs.github.io/docir/run-781485012ad0.html) | `disable_types` frees the prefix, then documents are retyped one at a time — keeping every id |
| [Connect an agent to docir](https://l0kifs.github.io/docir/run-00b9e9f30914.html) | The CLI skill or the bundled MCP server — transports, tool names, and why both answer identically |
| [How to read a ranked result](https://l0kifs.github.io/docir/ref-0e14d7c32dbf.html) | `score` vs `similarity`, what `--min-score` filters, and the two hits it never drops |
| [Every ADR and architecture note](https://l0kifs.github.io/docir/index.html) | The design rationale as documents — or `docir query --type decision` |

## Architecture

Vertical bounded-context **modules** (`documents`, `tags`, `indexing`, `agents`,
`publishing`, `release`) over a shared **platform**, wired by thin **entry_points**.
Dependencies flow `entry_points → modules → platform → config`; boundaries are enforced
by [tach](https://docs.gauge.sh) in CI — not by convention. Each module exposes exactly
one public file (`api.py`) described by a `CONTRACT.md`.

The design rationale and the module rules are themselves docir documents — run
`docir get arch-1cfb1b212237 arch-322e5f992ad2`, or browse
[`.docir/docs/architectures/`](.docir/docs/architectures/). [`docs/README.md`](docs/README.md)
maps every pre-migration path to its id.

## Support

Questions and half-formed ideas go to
[Discussions](https://github.com/l0kifs/docir/discussions); a reproducible bug goes to
[Issues](https://github.com/l0kifs/docir/issues). Either way, every command prints JSON when
its output is captured, so `docir check | cat` is already a complete report to paste.
Anything exploitable goes through a private advisory instead — see the
[security policy](.github/SECURITY.md).

## Contributing

Issues and PRs welcome. docir dogfoods itself: its ADRs, architecture documents, runbooks
and gap register live in its own store, so `docir context "what you are about to change"`
is how you orient, and every design deviation is recorded as an ADR rather than written by
hand. Module boundaries are machine-checked by [tach](https://docs.gauge.sh) in CI, alongside
lint, type-check, dead-code scan, contract sync and a coverage gate.

```bash
uv sync                                              # dev environment
uv run pytest --cov=docir --cov-fail-under=90        # tests + coverage gate
```

The full gate suite, the benchmark harnesses and the module rules are in
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT © Sergei Konovalov
