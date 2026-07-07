# docir

## Why the name

**docir** = **doc**uments as **IR**.

"IR" stands for *intermediate representation* — a term from compilers. The name captures the core architecture: markdown sources are **compiled** into a verifiable index, exactly the way a compiler turns source code into an intermediate representation. Files are the *source*; the SQLite index is the *derived* (compiled) artifact.

## What it is

A CLI for git-backed markdown documents (decisions, issues, architecture notes)
with a derived, read-optimized index. Git is the source of truth; the SQLite
index (metadata + FTS5 full-text + relation graph + semantic embeddings) is a
rebuildable projection. AI agents never edit markdown directly — every write
goes through the CLI, which guarantees frontmatter/schema consistency.

See [docs/doc-index-architecture.md](docs/doc-index-architecture.md) for the
full design.

## Architecture

The codebase follows Clean Architecture, with dependencies pointing strictly
inward:

| Layer | Package | Responsibility |
|---|---|---|
| Presentation | `docir.presentation` | Typer + Rich CLI; the composition root wiring adapters into use cases |
| Application | `docir.application` | Use cases (document / tag / maintenance) and the request/response boundary |
| Domain | `docir.domain` | Entities, value objects, ports, and pure services (validation tiers, scoring, graph checks) |
| Infrastructure | `docir.infrastructure` | SQLAlchemy index + Alembic, filesystem store, embedders, and the Unix-socket daemon |

The daemon keeps the embedding model warm and serializes writes; the CLI stays
a thin, stateless client that transparently spawns and respawns it. A
`RequestExecutor` port lets the same commands run either in-process
(`--no-daemon`) or over the socket.

## Install & use

```bash
uv sync                       # create the environment
uv run docir tag add auth --description "Authentication and tokens."
uv run docir add --type decision --title "Auth strategy" \
    --description "How the service authenticates API clients." \
    --tags auth --stdin < draft.md
uv run docir context "implement a new auth endpoint"   # ranked relevant set
uv run docir --help                                    # all commands
```

All state lives under `~/.docir/` (override with `DOCIR_HOME`).

## Development

```bash
uv run ruff check . && uv run ruff format --check .   # lint + format
uv run ty check                                        # type check
uv run vulture                                         # dead-code scan
uv run pytest --cov=docir --cov-fail-under=90          # tests + coverage
```
