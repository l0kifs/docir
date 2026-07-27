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

Switching embedders re-embeds rather than mixing vector spaces: docir records which model
produced each vector, ignores the others, and recomputes them on the next write or
`docir embed --flush`.

## Quickstart

```bash
# 1. install
uv tool install docir          # or: pipx install docir

# 2. scope docs to this repo (creates ./.docir, like `git init`)
docir init

# 3. teach this repo's AI agent to drive docir (writes a Claude Code skill)
docir agent install            # add --agent agents for an AGENTS.md block

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
[{"id":"adr-0001","title":"Auth strategy","description":"How the service authenticates API clients.","type":"decision","status":"proposed","tags":["auth"],"archived":false,"stale":false,"score":0.0328,"via_graph":false}, ...]
```

*An absent field means its default (no owner, not stale); the relevance `score` is a
reciprocal-rank fusion of the full-text and vector rankings, so ordering is the point and
the absolute value means little. `--json`
forces JSON anywhere, `--pretty` forces the table, `--no-trim` keeps every field.*

## The model

- **Git is the source of truth.** The index is a compile artifact — derived,
  `.gitignore`d, rebuildable. Nothing lives only in the database.
- **One write path.** Agents never edit markdown directly; every write goes through the
  CLI, which guarantees frontmatter/schema consistency and collision-free id allocation.
- **Reads return skeletons.** `query` / `search` / `context` return frontmatter + typed
  edges + staleness — *no body*. Fetch bodies by id with `get`. An agent scans wide cheaply,
  then reads deep only where it matters.
- **Staleness is data, not a guess.** Optional `owner` / `verified` fields plus a per-type
  review cadence make "is this doc still true?" a first-class, checkable fact (`docir check`).
- **Relations are typed.** A `related` edge carries a *kind* (`supersedes`, `depends_on`,
  `implements`, …) — a real graph, not a bag of links.

## Commands

| Command | What it does |
|---|---|
| `docir init` | Scope docs to a project-local `./.docir` store (like `git init`) |
| `docir add` | Create a document — the single write path |
| `docir update` | Edit content, metadata, or relations of an existing document |
| `docir context <query>` | Ranked relevant set (skeletons) — full-text + vector, fused |
| `docir search` / `query` | Full-text search / structured filter (skeletons) |
| `docir get <id>` | Full document with body |
| `docir check` | Structural findings — duplicate ids, dangling edges, staleness (`--strict` gates CI on errors, `--fix` repairs them) |
| `docir agent install` | Teach this repo's AI agent to drive docir |

### Full command reference

```
init · add · update · archive · unarchive · delete
get · query · search · context
tag {add, list, rename, rm}
agent {install, update}
schema {show, validate}
check [--fix] · lint · reindex · embed · version
daemon serve
```

Store precedence (highest first): `--home` → `DOCIR_HOME` → a project-local `.docir/`
found by walking up from the CWD → the global `~/.docir` default. `--no-daemon` runs any
command in-process instead of over the daemon socket. Output is a Rich table at a TTY and
compact JSON when piped; `--json` / `--pretty` force either, and `--no-trim` keeps every field.
That applies to `--help` too — `docir --help | cat` returns the command vocabulary as JSON,
so an agent can discover the CLI without parsing box-drawing characters.

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

See [docs/doc-index-architecture.md](docs/doc-index-architecture.md) for the design
rationale and [docs/architecture-rules.md](docs/architecture-rules.md) for the module rules.

## Contributing

Issues and PRs welcome. Read the [architecture rules](docs/architecture-rules.md) and the
[ADRs](docs/adr/) first — module boundaries are machine-checked by [tach](https://docs.gauge.sh)
in CI, alongside lint, type-check, and a coverage gate. Every design deviation is recorded
as an ADR.

```bash
uv sync                                              # dev environment
uv run python benchmarks/run.py                      # retrieval quality + token cost
uv run pytest --cov=docir --cov-fail-under=90        # tests + coverage gate
uv run ruff check . && uv run ty check && uv run tach check
```

## License

MIT © Sergei Konovalov
