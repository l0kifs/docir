# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Read `README.md` first — it explains what `docir` is (markdown compiled into a derived index),
the file format, the CLI surface, and the read/write flows. Read
[`docs/doc-index-architecture.md`](docs/doc-index-architecture.md) for the design rationale and
[`docs/architecture-rules.md`](docs/architecture-rules.md) for the module rules this codebase is
held to. This file covers what those do not: commands, the module boundaries and how they are
machine-checked, and invariants that look like cruft but are load-bearing.

## Commands

One `uv`-managed package, Python 3.12+. All state lives under `~/.docir/` (`DOCIR_HOME` overrides).

```bash
uv sync                                          # create/refresh the environment
uv run docir --help                              # the CLI (agent contract)
uv run docir --no-daemon <cmd> ...               # run in-process, bypass the daemon

# the full CI gate suite — run ALL of these before reporting work done:
uv run ruff check . && uv run ruff format --check .   # lint + format
uv run ty check                                        # type check (Astral ty)
uv run vulture                                         # dead-code scan
uv run tach check                                      # module boundaries (§8)
uv run python scripts/check_contract_sync.py           # api.py <-> CONTRACT.md (§8.6)
uv run pytest --cov=docir --cov-fail-under=90          # tests + coverage (currently 94%)
```

- **`tach check` exits 0 even though it prints `[WARN] ... deprecated` lines.** Those warnings are
  the intended baseline (see "The shared-index baseline" below), not failures. A real boundary
  break exits non-zero.
- A **tach pytest plugin auto-runs** on `uv run pytest` (the `[Tach]` banner). It does test-impact
  analysis; it does not change results. `-p no:tach` disables it; `--tach` runs only impacted tests.
- **Single tests:** `uv run pytest tests/modules/documents/test_integration_documents.py -k archive`.
  The daemon end-to-end tests are marked `slow` and spawn a real subprocess:
  `uv run pytest -m "not slow"` skips them.
- **Real embeddings** (ONNX, off by default): `uv sync --extra embeddings` then
  `DOCIR_EMBEDDER=fastembed`. Everything otherwise uses the deterministic embedder so tests stay
  hermetic and dependency-light.

## Architecture

Two theses run through the whole system; most "why is it like this?" questions resolve to one of them.

**1. Git is the source of truth; the SQLite index is a derived, rebuildable projection.** Nothing
lives only in the database — `docir reindex` rebuilds it from the files. The markdown files (plus
`docs/tags.yaml`) are canonical and diff cleanly in git; the index (metadata + FTS5 + relation
graph + embedding BLOBs) is a compile artifact, `.gitignore`d. When in doubt, the files win.

**2. Agents never edit markdown directly — every write goes through the CLI.** That single write
path is what guarantees frontmatter/schema consistency and id allocation without collisions. Adding
a write that bypasses it defeats the point.

The daemon exists only to keep the embedding model warm and serialize writes; the CLI is a thin,
stateless client that transparently spawns/respawns it. The same command runs either in-process
(`--no-daemon`) or over a Unix socket through one `RequestExecutor` boundary
(`platform/transport/messages.py`) — the `Dispatcher` (`entry_points/dispatch.py`) is the single
place that knows the command vocabulary, so the wire contract and the local contract cannot drift.

### Module layout (enforced, not aspirational)

The codebase is vertical bounded-context **modules** over shared **platform** capabilities, wired by
thin **entry_points** — the shape `docs/architecture-rules.md` mandates. `tach` proves it in CI.

```
src/docir/
├── config/        settings + ~/.docir path layout
├── platform/      errors · clock · embedding · persistence · filesystem · transport   (shared, technical)
├── modules/
│   ├── documents/   api.py + CONTRACT.md + domain/application/infra   (the document aggregate; write + read + maintenance)
│   ├── tags/        api.py + CONTRACT.md + domain/application          (the tag registry)
│   └── indexing/    api.py + CONTRACT.md + domain/application/infra    (hybrid ranking + the embedding scheduler)
└── entry_points/  cli · daemon · composition · dispatch                (wiring only, no business logic)
```

Dependencies flow **`entry_points → modules → platform → config`**, and between modules only
**`tags → documents → indexing`**. There are no cycles, and tach fails the build if you introduce one.

- **Each module exposes exactly one public file, `api.py`.** Code outside a module (entry_points, or
  another module) may import **only** that module's `api`, never its `domain`/`application`/`infra`.
  This is enforced by the tach dependency graph in `tach.toml`: each layer of each module is its own
  tach module, and the internals are simply never listed as an allowed dependency of outside code.
- **`domain/` is pure** — no I/O, no frameworks, no `platform` services beyond pure primitives (the
  error taxonomy, the `Embedding` value object). tach enforces this; if domain code needs a
  repository or a clock, it belongs in `application/`.
- Every `api.py` has a `CONTRACT.md` beside it. **A change to `api.py` and its `CONTRACT.md` must
  land in the same commit** — `scripts/check_contract_sync.py` fails the build otherwise (§8.6).
- New modules, merges/splits, platform additions, or deliberate rule violations get an ADR in
  `docs/adr/` (§14). Read them — they explain the deviations below.

### The shared-index baseline (read before touching persistence)

`docir` keeps a **single shared SQLite schema and one `UnitOfWork`** spanning all three contexts, so
a file write and its metadata/FTS/relation update commit atomically. A strict reading of the rules
(§5.1/§5.3, one owner per table, no shared transaction) would forbid that; going fully compliant
means per-module storage plus an event bus, which is a rewrite the project deliberately deferred
(**ADR-0002**). The consequences you will see:

- The repositories, unit-of-work, models, and file stores live in `platform/persistence` and
  `platform/filesystem`, and they map each context's domain entities — so `platform → *.domain`
  edges exist. These are declared `deprecated = true` in `tach.toml`: they are the **ratchet
  baseline** (§8.1/§12.1), reported on every run, allowed only to shrink.
- **Do not add a new `platform → module` edge, a new cross-module edge, or a `tach-ignore`.** The
  sanctioned responses to a boundary error are: route through the module's `api`, move the shared
  thing into `platform`, or (last resort) merge the modules — never widen a baseline. Shrinking it
  (splitting the index per module behind events) is the only allowed direction and would supersede
  ADR-0002.
- All cross-context *data* access goes through `platform` (the shared repos), not through another
  module's code. That is why `tags` imports nothing from `documents` even though tag rename rewrites
  documents — it reaches them via `uow.documents`, keeping the module graph acyclic.

## Invariants worth preserving

- **Embeddings are the one deferred, eventually-consistent piece.** A content change sets an
  `embedding_dirty` flag (persisted, survives a daemon restart) and returns; everything else (file,
  metadata, FTS, relations) is synchronous and current when the command returns. Two scheduler
  implementations back this: `InlineEmbeddingScheduler` (in-process/tests, drains synchronously so
  behaviour is deterministic) and `ThreadedEmbeddingScheduler` (daemon, debounced background thread).
  Anything that needs the vector *now* must flush: `--wait-embeddings` on a write, `docir embed
  --flush`, or `docir reindex --embeddings`. Do not move embedding onto the synchronous write path.
- **Ids are allocated from the DB counter (`SequenceRow`), never by scanning files** — that is what
  keeps parallel agents from minting the same id. Conversely, `docir check`'s duplicate-id detection
  scans the *files* directly (`MaintenanceService._find_duplicate_ids`), because two files sharing an
  id are invisible in the index (it dedupes by primary key). That scan is the merge-into-`main`
  guard; `docir check --strict` exits 1 for CI.
- **Validation is three tiers and mixing them is the documented overengineering trap.** Tier 0 is a
  hard, synchronous compiler-style gate (missing field, bad status/transition, unknown tag/related,
  unknown/disallowed relation kind); Tier 1 (`docir check`) is non-blocking structural graph warnings
  (incl. **staleness** and **unknown-type**); Tier 2 (`docir lint --deep`) is advisory heuristics (embedding similarity,
  scope creep). Never promote a heuristic to a hard error.
- **Relation edges are typed (ADR-0005).** `related` entries carry a `kind` (`RelatedRef{target,
  kind}`); the on-disk form is a bare id for the default `relates_to` (so pre-typed files round-trip
  unchanged) or a `{to, kind}` mapping. `relations.kind` is a **non-key** column — one kind per
  ordered `(source, target)` pair — added by migration `0002`. The `relation_types` registry is
  **permissive when empty** (schemas predating typed edges accept any kind). Per-type
  `allowed_relations` is a whitelist enforced at Tier 0.
- **Staleness is data, not a heuristic (ADR-0006).** Optional `owner`/`verified` frontmatter +
  per-type `review_days`; `docir check` emits a Tier 1 `stale` finding and read views carry a `stale`
  flag. `MaintenanceService`/`DocumentService` need a `Clock` for "today". **AST-anchored** staleness
  is intentionally *not* built — human `--verified` is the honest baseline; anchoring is a future
  additive layer.
- **Read paths return skeletons (two-tier retrieval).** `query`/`search`/`context` return
  `DocumentSummary` (frontmatter + typed edges + staleness, **no body**); only `get` returns the full
  `DocumentView` with the body. Do not add the body back to the list paths — the skeleton is the
  context-saving contract.
- **The schema is core + profiles (ADR-0007).** `infra/profiles.py` holds a frozen domain-agnostic
  core (the `decision` type + relation registry + cadences) and bundled profiles (software/research/
  ops/legal). A `docs-schema.yaml` with a `profiles:` key merges `core -> profiles -> inline`; a file
  with no `profiles:` key parses inline-only (fully backward compatible). The default is
  `profiles: [software]`, which resolves to exactly `decision`/`issue`/`architecture`. The core is
  always merged when a `profiles:` key is present (you can't disable it that way); disabling a
  profile after its docs exist leaves them with a type the schema no longer knows — `docir check`
  flags those as `unknown-type` (schema resolution does not re-key or migrate existing files).
- **Alembic owns the schema and must sit beside the engine.** `run_migrations`
  (`platform/persistence/engine.py`) resolves the migration dir via `Path(__file__).parent /
  "alembic"`; moving `engine.py` without the `alembic/` folder silently breaks migrations. The FTS5
  virtual table is **raw DDL in migration `0001`, not an ORM model** — it is queried through
  SQLAlchemy Core `text()` in `SqlAlchemySearchIndex`. `alembic/` is excluded from ruff/ty/tach/
  coverage on purpose.
- **SQLite foreign keys are enabled per-connection** by a `PRAGMA foreign_keys=ON` event listener in
  `create_index_engine`. The `ON DELETE CASCADE` from `relations`/`document_tags`/`embeddings` to
  `documents` depends on it; a raw connection without that listener will orphan rows.
- **The daemon socket path is derived, short, and outside `DOCIR_HOME`** — `Path(tempfile.gettempdir())
  / f"docir-{sha1(home)[:12]}.sock"`. A deep home path would blow past the ~104-char `AF_UNIX` limit,
  so the socket cannot live under it; the hash keeps it stable per installation. The pid and log files
  *do* live under `DOCIR_HOME`.
- **The daemon is disposable and respawned** by the client (`entry_points/daemon/lifecycle.py`); it
  self-shuts-down after an idle timeout. It is spawned as a detached `python -m docir daemon serve`,
  so `src/docir/__main__.py → entry_points.cli.app:main` and the hidden `daemon serve` command must
  keep working. `daemon serve` builds a container with `background_embeddings=True`.
- **All exceptions live in `platform/errors`.** `DocirError` is the base and carries an `exit_code`;
  `entry_points/cli/runner.py` maps that onto the process exit code. Raise a typed subclass, not a
  bare `DocirError`, so the CLI reports the right code.
- **`fastembed` is optional and quarantined.** `platform/embedding/fastembed.py` imports a
  not-necessarily-installed dependency, so it is excluded from `ty` and omitted from coverage
  (`pyproject.toml`), and imported lazily only when `DOCIR_EMBEDDER=fastembed`. The deterministic
  embedder is the default everywhere else.

## Testing

Central `tests/` tree, organized to mirror the modules (**ADR-0004** — tests are not yet co-located
inside `src/docir/modules/**`, a recorded deviation from §9):

```
tests/
├── conftest.py                 shared fixtures (see below)
├── modules/{documents,tags,indexing}/
├── platform/                   persistence · filesystem · embedding
├── config/
└── entry_points/               executor + the slow e2e CLI/daemon tests
```

- **Everything is hermetic via `conftest.py`.** The `settings` fixture points `DOCIR_HOME` at a
  `tmp_path`, forces `DOCIR_NO_DAEMON`, and clears `DOCIR_EMBEDDER`. `container`/`dispatcher` build
  the in-process object graph with a `FixedClock` (frozen date) and `background_embeddings=False` —
  so timestamps are deterministic and embeddings drain synchronously. `uow_factory` is the
  persistence-level seam; `seeded` gives you two tags + two related docs.
- Test through the seams the layer test-table prescribes: pure unit tests for `domain/`, the
  `dispatcher`/`container` fixtures for use cases and contract tests, real SQLite for `infra/`, and
  the `slow` subprocess tests for end-to-end. Prefer in-memory fakes over mocks for ports.
- Keep the regression-guard style: when a test pins a subtle bug, name the bug in a comment (e.g.
  `test_merge_safety.py` guards duplicate ids a branch merge produces).
- The coverage gate is **90%** (`--cov-fail-under=90`); `alembic/` and `fastembed.py` are omitted.

## Known rough edges / recorded deviations

Real, documented, not stylistic — don't be surprised, and don't paper over them silently:

- **The shared index/UoW is a deviation, not the target end-state (ADR-0002).** `platform` is not a
  pure leaf; the `platform → *.domain` tach edges are the baseline that must only shrink. The
  intended future move is per-module storage fed by domain events, which removes them.
- **No authorization / cross-cutting machinery (ADR-0003).** `docir` is a single-user local CLI with
  no actors or permissions, so §6/§6.1 are intentionally not instantiated. If it ever grows real
  actors, a cross-cutting concern must be introduced per §6.
- **Tests are centralized, not inside their modules (ADR-0004).** The next sanctioned refactor is to
  co-locate them under `src/docir/modules/**`.
- `MaintenanceService` (reindex/check/lint) lives in `documents` and reaches the search/embedding
  index through `indexing.api` and the shared UoW; it is the one genuinely cross-cutting operation,
  which is why it sits in the module that owns the aggregate rather than in its own module.
