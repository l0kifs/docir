<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/l0kifs/docir/main/assets/logo/docir-lockup-dark.png" />
  <img src="https://raw.githubusercontent.com/l0kifs/docir/main/assets/logo/docir-lockup.png" alt="docir" width="260" />
</picture>

**doc**uments as **IR** — a CLI that *compiles* git-backed markdown<br />into a verifiable, read-optimized index for AI coding agents.

[![PyPI](https://img.shields.io/pypi/v/docir)](https://pypi.org/project/docir/) [![Python](https://img.shields.io/pypi/pyversions/docir)](https://pypi.org/project/docir/) [![CI](https://img.shields.io/github/actions/workflow/status/l0kifs/docir/ci.yml?branch=main)](https://github.com/l0kifs/docir/actions) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[The idea](#the-idea) · [Quickstart](#quickstart) · [Why not just…](#why-not-just) · [Commands](#commands) · [Docs](docs/)

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

### † What semantic retrieval costs you

Semantic search runs on a real embedding model, installed by default. It is quantized,
CPU-only, and runs locally — nothing is sent anywhere — but it is not free:

| | |
|---|---|
| Model | `BAAI/bge-small-en-v1.5`, 384-dim, quantized ONNX |
| Download | **~64 MB**, once, on first use — the only step that needs network |
| Install | **~240 MB** of dependencies (`onnxruntime`, `numpy`, `tokenizers`, …) |
| Runtime | CPU only, no GPU, no API key; the daemon keeps the model warm |
| Window | ~512 tokens (~1,900 chars) — which is why docir embeds **per section**, below |

If that is too heavy — a CI image, a container you keep small, an air-gapped box — opt out
and docir falls back to a dependency-free hashing embedder:

```bash
export DOCIR_EMBEDDER=deterministic
```

That embedder scores similarity by *shared vocabulary* rather than meaning, which is the
same signal the full-text index already provides. The cost is measured, not asserted:
`docir context` scores **recall@5 0.96** with the model against **0.93** without it, and puts
the right document first far more often (**MRR 0.95 vs 0.80**). Isolate the embedding signal
by turning graph expansion off, and on questions phrased in words the documents never use the
model gets **0.86** where the fallback gets **0.79** — below the 0.79 that plain full-text
search manages on its own. Corpus, tasks, judgments and caveats are in
[benchmarks/](benchmarks/); `uv run python benchmarks/run.py` reproduces it.

### Long documents are embedded per section

The model reads about 512 tokens — roughly 1,900 characters — and silently ignores
the rest. Not downweights: ignores. Append a sentence past that point and the
vector comes back bit-identical. 84 of the 103 documents in docir's own store are
longer than that, so **56% of the corpus was not in the semantic index at all** —
and nothing said so, because full-text search covers the whole body and rescued
the rank on any query that shared a word with the document.

docir therefore embeds **each `##` section as well as the whole document**
(ADR-0014), and a document ranks on its best-matching section. Coverage on
docir's own store: **44% → 100%**. On the same corpus, `context` recall@5 holds at
0.97 while MRR rises 0.94 → 0.97. `benchmarks/run.py` reports the coverage figure
and measures the window empirically, so it stays honest if the model changes.

Reading follows ranking: if `context` surfaced a document for one of its
sections, read that section rather than the whole file.

```bash
docir get arch-1cfb1b212237 --section "Daemon process"
```

It returns the same span `update --replace-section` would overwrite, and an
unknown heading errors listing the ones that exist.

Switching embedders re-embeds rather than mixing vector spaces: docir records which model
produced each vector, ignores the others, and recomputes them on the next write or
`docir embed --flush`.

## Quickstart

```bash
# 1. install
uv tool install docir          # or: pipx install docir

# 2. scope docs to this repo (creates ./.docir, like `git init`)
#    skip it and docs go to the global ~/.docir — docir warns if you are in a repo
docir init

# 3. teach this repo's AI agent to drive docir (writes a Claude Code skill)
docir agent install            # add --agent agents for an AGENTS.md block
                               # (or, for an MCP client: docir mcp serve)

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

*An absent field means its default (no owner, not stale). `score` is a reciprocal-rank
fusion of the full-text and vector rankings, so ordering is the point and the absolute
value means little — a nonsense query against a one-document store scores about the same
as a perfect match. `similarity` is the raw cosine against your query and does carry
absolute meaning, which is what `--min-score` filters on: with it, an empty result is a
real answer rather than an impossible one. `--json` forces JSON anywhere, `--pretty`
forces the table, `--no-trim` keeps every field.*

### Scope and limits

- **Search covers title, description and body — not tags.** Tags are a controlled vocabulary
  for `docir query --tag`, deliberately kept out of the full-text index so one tag match
  cannot flood out the text matches. `docir search auth` will not find a document merely
  tagged `auth`.
- **List paths page.** `query`, `search` and `tag list` take `--limit` and `--offset`, applied
  in the query rather than after it. A page shorter than `--limit` means the end; there is no
  total, because the response is a bare JSON array.
- **`context` is not paged, by design.** It returns a minimal relevance-ranked set bounded by
  `--limit` — a token budget, not a browse path. It does load every current embedding per
  call, which is what sets the practical corpus ceiling.
- **Dates are UTC calendar dates.** `created`, `updated` and `verified` are written into
  committed files and read by other people, so they do not depend on the writer's timezone.

## The model

- **Git is the source of truth.** The index is a compile artifact — derived,
  `.gitignore`d, rebuildable. Nothing lives only in the database.
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

### What you may edit by hand

The files are git-backed markdown and `docir reindex` exists precisely to pick up an
outside change — so hand-editing is supported, but not on every field:

| | by hand | instead |
|---|---|---|
| document **body** | ✅ | — |
| `docs-schema.yaml`, `docs/tags.yaml` | ✅ | no CLI write path for the schema |
| `tags`, `status`, `related`, `type` | ❌ | `docir update --set-tags / --status / --set-related` |
| `id` | ❌ never | it is the primary key; changing it orphans every inbound link |
| `verified` | ❌ never | `docir update <id> --verified` — it asserts a human re-read the doc |

**Then run `docir reindex && docir check`** — or let the daemon do the reindex for
you. It watches `.docir/docs/` and rebuilds what changed within a second of the
edit, which is safe precisely because the files are canonical: a reindex only
makes the index agree with them, and writes no markdown. `DOCIR_WATCH=0` turns it
off; `--no-daemon` runs never watch, so CI still needs the explicit command.
`docir check` is still yours to run. Reindex reports `documents_skipped` for files
whose frontmatter will not parse — those are absent from every read path, not merely
flagged — and `check` catches unregistered tags, undeclared statuses, unknown types,
dangling links and duplicate ids. A hand-written `verified` date is the one thing nothing
can verify, which is exactly why it should not be written by hand.

## Commands

| Command | What it does |
|---|---|
| `docir init` | Scope docs to a project-local `./.docir` store (like `git init`) |
| `docir add` | Create a document — the single write path |
| `docir update` | Edit content, metadata, or relations of an existing document |
| `docir context <query>` | Ranked relevant set (skeletons) — full-text + vector, fused (`--min-score` to filter noise) |
| `docir search` / `query` | Full-text search (title/description/body — **not tags**) / structured filter. Both page with `--limit`/`--offset`; `query --owner X --stale` is a review queue |
| `docir get <id>` | Full document with body — or one section with `--section "<heading>"` |
| `docir check` | Structural findings — duplicate ids, dangling edges, staleness (`--strict` gates CI on errors, `--fix` repairs them) |
| `docir agent install` | Teach this repo's AI agent to drive docir |
| `docir mcp serve` | Serve the same commands as MCP tools, for a client that speaks MCP |

### Full command reference

```
init · add · update · archive · unarchive · delete
get · query · search · context
tag {add, list, rename, rm}
agent {install, update}
schema {show, validate}
check [--fix] · lint · reindex · embed · version
daemon serve · mcp serve
```

Store precedence (highest first): `--home` → `DOCIR_HOME` → a project-local `.docir/`
found by walking up from the CWD → the global `~/.docir` default. `--no-daemon` runs any
command in-process instead of over the daemon socket. Output is a Rich table at a TTY and
compact JSON when piped; `--json` / `--pretty` force either, and `--no-trim` keeps every field.
That applies to `--help` too — `docir --help | cat` returns the command vocabulary as JSON,
so an agent can discover the CLI without parsing box-drawing characters.

## Two ways an agent reaches docir

Some agents run shell commands; some only call MCP tools. Both get the same
vocabulary, because both go through the same dispatcher — an MCP tool and its
CLI command cannot answer differently.

```bash
docir agent install               # a Claude skill / an AGENTS.md block: drive the CLI
claude mcp add docir -- docir mcp serve   # or the same commands as MCP tools
```

`docir mcp serve` speaks stdio (what an MCP client spawns) or `--transport http`,
and needs no extra — the MCP server ships with docir, because an agent that only
speaks MCP cannot install the extra it would need to reach docir in the first
place. `uvx docir mcp serve` runs it without installing anything.

The tools are named `docir_context`, `docir_get`, `docir_add`, … Reads carry the
`readOnlyHint` annotation and return the same body-less skeletons the CLI does,
trimmed the same way; requests go through the daemon by default, so the
embedding model stays warm across calls.

## How state is stored

State lives in one resolved store per invocation. Run `docir init` in a repo to keep its
docs with the code: `.docir/docs/` and `docs-schema.yaml` are **committed**; the derived
index (SQLite + embeddings) is **gitignored** and rebuilds with `docir reindex`. Without
`init`, docir falls back to a global `~/.docir`.

The daemon keeps the embedding model warm and serializes writes; the CLI is a thin,
stateless client that spawns and respawns it transparently. Embeddings are the one
deferred, eventually-consistent piece — a content change flags the vector dirty and returns;
everything else (file, metadata, FTS, relations) is synchronous. Force a flush with
`--wait-embeddings`, `docir embed --flush`, or `docir reindex --embeddings`.

## Schema: core + profiles

Documents are constrained by a per-type schema (required fields, status grammar, allowed
relations). docir ships a frozen, domain-agnostic **core** plus swappable **profiles** —
`software` (default: `decision` / `issue` / `architecture` / `release_note`), `research`,
`ops`, `qa`, `legal`. A `docs-schema.yaml` merges `core → profiles → inline`, so you extend
it without mutating the base.

```bash
docir init --profiles software,qa   # pick profiles up front
docir init --id-style sequential    # readable adr-0007 instead of the default random
docir schema show                   # the merged result — what validation enforces
docir schema validate               # check an edit before it reaches a write
```

`docir init` writes `id_style: random` by default — ids like `adr-3f9a2b1c7d4e`, which two
branches can never mint identically. Pass `--id-style sequential` for human-friendly
`adr-0007` numbering; it is collision-free within one store, but a merge can bring two
branches that each allocated the same number (`docir check` reports it as `duplicate-id`).

The generated `docs-schema.yaml` carries a commented-out worked example of the inline
`types:` / `relation_types:` syntax, so the grammar is discoverable at the point of use.

## Architecture

Vertical bounded-context **modules** (`documents`, `tags`, `indexing`, `agents`) over a
shared **platform**, wired by thin **entry_points**. Dependencies flow
`entry_points → modules → platform → config`; boundaries are enforced by
[tach](https://docs.gauge.sh) in CI — not by convention. Each module exposes exactly one
public file (`api.py`) described by a `CONTRACT.md`.

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
uv run pytest --cov=docir --cov-fail-under=90        # tests + coverage gate
uv run ruff check . && uv run ty check && uv run tach check
```

## License

MIT © Sergei Konovalov
