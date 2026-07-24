# docir

## Why the name

**docir** = **doc**uments as **IR**.

"IR" stands for *intermediate representation* — a term from compilers. The name captures the core architecture: markdown sources are **compiled** into a verifiable index, exactly the way a compiler turns source code into an intermediate representation. Files are the *source*; the SQLite index is the *derived* (compiled) artifact.

## What it is

A CLI for git-backed markdown documents (decisions, issues, architecture notes)
with a derived, read-optimized index. Git is the source of truth; the SQLite
index (metadata + FTS5 full-text + a **typed** relation graph + semantic
embeddings) is a rebuildable projection. AI agents never edit markdown directly —
every write goes through the CLI, which guarantees frontmatter/schema consistency.

Documents are constrained by a per-type schema (required fields, status grammar,
and allowed relations); relation edges carry a *kind* (`supersedes`,
`depends_on`, `implements`, …); the read paths return body-less *skeletons* so an
agent scans cheaply and fetches bodies by id; a per-type review cadence plus
`owner`/`verified` fields make staleness explicit; and a frozen domain-agnostic
**core** plus swappable **profiles** (software / research / ops / legal)
generalize it beyond software without mutating the base schema.

See [docs/doc-index-architecture.md](docs/doc-index-architecture.md) for the
full design.

## Architecture

The codebase is organized as vertical bounded-context **modules** over shared
**platform** capabilities, wired by thin **entry_points**, following
[docs/architecture-rules.md](docs/architecture-rules.md). Module boundaries are
enforced by [tach](https://docs.gauge.sh) in CI. Each module exposes exactly one
public file (`api.py`) described by a `CONTRACT.md`.

### Modules (`src/docir/modules/`)

| Module | Purpose |
|---|---|
| `documents` | The document lifecycle — content, metadata, relations; the single write path and the read paths (get / query / search / context) plus index maintenance. |
| `tags` | The tag registry — the controlled vocabulary that classifies documents, kept consistent across every document that uses it. |
| `indexing` | The relevance engine — hybrid lexical + semantic ranking for context retrieval and the deferred embedding-recompute scheduler. |
| `agents` | Installs the AI-assistant instructions that teach a coding agent to drive docir — a Claude Code skill and/or an `AGENTS.md` block, from one packaged template. |

### Shared layers

- `platform/` — technical capability shared by all modules: `persistence`
  (SQLAlchemy index + Alembic + unit-of-work), `filesystem` (canonical markdown
  / `tags.yaml` stores), `embedding`, `transport` (the Unix-socket protocol),
  `clock`, `errors`.
- `config/` — runtime settings and the `~/.docir` path layout.
- `entry_points/` — the Typer CLI, the daemon worker, and the composition root
  that wires adapters into use cases. No business logic.

Dependencies flow `entry_points → modules → platform → config`, with
`tags → documents → indexing` between modules and no cycles. The daemon keeps
the embedding model warm and serializes writes; the CLI stays a thin, stateless
client that transparently spawns and respawns it. A `RequestExecutor` boundary
lets the same commands run either in-process (`--no-daemon`) or over the socket.

## Install & use

```bash
uv sync                       # create the environment
uv run docir tag add auth --description "Authentication and tokens."
uv run docir add --type decision --title "Auth strategy" \
    --description "How the service authenticates API clients." \
    --tags auth --stdin < draft.md
uv run docir context "implement a new auth endpoint"   # ranked relevant set
uv run docir agent install                             # teach this repo's AI agent to use docir
uv run docir --help                                    # all commands
```

`docir agent install` writes a Claude Code skill (`.claude/skills/docir/SKILL.md`);
add `--agent agents` for an `AGENTS.md` block, `--global` to install for every project,
and re-run `docir agent update` after upgrading docir. See
[docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md).

All state lives under `~/.docir/` (override with `DOCIR_HOME`).

## Development

```bash
uv run ruff check . && uv run ruff format --check .   # lint + format
uv run ty check                                        # type check
uv run vulture                                         # dead-code scan
uv run tach check                                      # module boundaries
uv run python scripts/check_contract_sync.py           # api.* <-> CONTRACT.md
uv run pytest --cov=docir --cov-fail-under=90          # tests + coverage
```
