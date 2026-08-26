# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Read `README.md` first — it explains what `docir` is (markdown compiled into a derived index),
the file format, the CLI surface, and the read/write flows.

**docir's own documentation lives in docir.** The ADRs, the architecture documents, the
runbooks and the gap register are documents in the project store (`.docir/docs/`), so read
them through the CLI rather than by path:

```bash
docir get arch-1cfb1b212237        # Doc-Index CLI — Architecture (the shape; links the five below)
docir get arch-322e5f992ad2        # Architecture Rules — Modular DDD (the module rules)
docir query --type decision        # every ADR (a document's id is its only address)
docir context "<what you are about to change>"   # ranked skeletons, no bodies
```

Ids are random, so [`docs/README.md`](docs/README.md) holds the stable old-path → id map.
This file covers what those documents do not: commands, the module boundaries and how they
are machine-checked, and invariants that look like cruft but are load-bearing.

## Commands

One `uv`-managed package, Python 3.12+. State lives in a single resolved store per invocation.
Home precedence (highest first): `--home` → `DOCIR_HOME` → a project-local `.docir/` discovered by
walking up from the CWD (created by `docir init`; the git model) → the global `~/.docir` default
(adr-20eec6e2e2ca). Discovery is inert whenever a home is explicitly given (every test sets `DOCIR_HOME`).

```bash
uv sync                                          # create/refresh the environment
uv run docir --help                              # the CLI (agent contract)
uv run docir --no-daemon <cmd> ...               # run in-process, bypass the daemon

# the full CI gate suite — run ALL of these before reporting work done:
uv run ruff check . && uv run ruff format --check .   # lint + format
uv run actionlint                                      # GitHub Actions workflows
uv run ty check                                        # type check (Astral ty)
uv run vulture                                         # dead-code scan
uv run tach check                                      # module boundaries (§8)
uv run python scripts/check_contract_sync.py           # api.py <-> CONTRACT.md (§8.6)
uv run python scripts/check_expressions.py <file.md>   # --expr examples actually run
uv run pytest --cov=docir --cov-fail-under=90          # tests + coverage (currently 95%)
```

- **`actionlint` is the only gate for a file that cannot be validated by running it.** A
  workflow parses as YAML long after GitHub would reject it — a job-level `env:` using the
  `runner` context is valid YAML and a workflow-file error, so *zero* jobs run and the failure
  says only "workflow file issue". It ships as `actionlint-py`, a wheel vendoring the Go
  binary, so the gate runs like every other one instead of needing Go or Docker. Run it before
  pushing a workflow change; a gate that only fires after the push cannot stop the push that
  turns main red.
- **`tach check` exits 0 even though it prints `[WARN] ... deprecated` lines.** Those warnings are
  the intended baseline (see "The shared-index baseline" below), not failures. A real boundary
  break exits non-zero.
- A **tach pytest plugin auto-runs** on `uv run pytest` (the `[Tach]` banner). It does test-impact
  analysis; it does not change results. `-p no:tach` disables it; `--tach` runs only impacted tests.
- **Single tests:** `uv run pytest tests/modules/documents/test_integration_documents.py -k archive`.
  The daemon end-to-end tests are marked `slow` and spawn a real subprocess:
  `uv run pytest -m "not slow"` skips them.
- **The real ONNX model is the default and a plain dependency** (adr-ab9c454b760c; the `embeddings` extra
  is gone). The test suite sets `DOCIR_EMBEDDER=deterministic` so it stays hermetic — which means
  most tests never touch a model, and anything about the model's *token window* cannot be tested
  that way: the hashing embedder has no window at all. Tests that need the real one are marked
  `slow` and clear the env var (`tests/modules/documents/test_chunked_retrieval.py`).

## Architecture

Two theses run through the whole system; most "why is it like this?" questions resolve to one of them.

**1. Git is the source of truth; the SQLite index is a derived, rebuildable projection.** Nothing
lives only in the database — `docir reindex` rebuilds it from the files. The markdown files (plus
`docs/tags.yaml`) are canonical and diff cleanly in git; the index (metadata + FTS5 + relation
graph + embedding BLOBs) is a compile artifact, `.gitignore`d. When in doubt, the files win.

**2. The CLI is the only write path.** That is what guarantees frontmatter/schema consistency
and id allocation without collisions. Adding a write that bypasses it defeats the point.

The daemon exists only to keep the embedding model warm and serialize writes; the CLI is a thin,
stateless client that transparently spawns/respawns it. The same command runs either in-process
(`--no-daemon`) or over a Unix socket through one `RequestExecutor` boundary
(`platform/transport/messages.py`) — the `Dispatcher` (`entry_points/dispatch.py`) is the single
place that knows the command vocabulary, so the wire contract and the local contract cannot drift.

### Module layout (enforced, not aspirational)

The codebase is vertical bounded-context **modules** over shared **platform** capabilities, wired by
thin **entry_points** — the shape `arch-322e5f992ad2` (Architecture Rules) mandates. `tach`
proves it in CI.

```
src/docir/
├── config/        settings + ~/.docir path layout
├── platform/      errors · clock · embedding · persistence · filesystem · transport   (shared, technical)
├── modules/
│   ├── documents/   api.py + CONTRACT.md + domain/application/infra   (the document aggregate; write + read + maintenance)
│   ├── tags/        api.py + CONTRACT.md + domain/application          (the tag registry)
│   ├── indexing/    api.py + CONTRACT.md + domain/application/infra    (hybrid ranking + the embedding scheduler)
│   ├── agents/      api.py + CONTRACT.md + domain/application/infra    (installs AI-assistant instructions; adr-3a2d5ee7bc84)
│   ├── publishing/  api.py + CONTRACT.md + domain/application/infra    (renders the corpus as a static site; adr-a343140d72e2)
│   └── release/     api.py + CONTRACT.md + domain/application/infra    (how docir was installed + is it current; adr-a555ee6bc484)
└── entry_points/  cli · daemon · mcp · composition · dispatch          (wiring only, no business logic)
```

Dependencies flow **`entry_points → modules → platform → config`**, and between modules only
**`tags → documents → indexing`**. There are no cycles, and tach fails the build if you introduce one.
`agents`, `publishing` and `release` are self-contained leaves (depending only on
`platform.errors`, and `release` on `platform.clock`); they own no index/DB state, so they have no
shared-index baseline edges. **`publishing` takes documents as
data — the `docir get` JSON shape — rather than importing `documents.api`**, which is what keeps it
a leaf: the site is a projection of the public contract, not a second reader of the aggregate. Do
not "simplify" it by handing it a `DocumentService`.

- **Each module exposes exactly one public file, `api.py`.** Code outside a module (entry_points, or
  another module) may import **only** that module's `api`, never its `domain`/`application`/`infra`.
  This is enforced by the tach dependency graph in `tach.toml`: each layer of each module is its own
  tach module, and the internals are simply never listed as an allowed dependency of outside code —
  so importing past `api.py` fails the build rather than a code review.
- **`domain/` is pure** — no I/O, no frameworks, no `platform` services beyond pure primitives (the
  error taxonomy, the `Embedding` value object). tach enforces this; if domain code needs a
  repository or a clock, it belongs in `application/`.
- Every `api.py` has a `CONTRACT.md` beside it. **A change to `api.py` and its `CONTRACT.md` must
  land in the same commit** — `scripts/check_contract_sync.py` fails the build otherwise (§8.6).
- New modules, merges/splits, platform additions, or deliberate rule violations get an ADR in
  the store as a `decision` document (§14) — `docir add --type decision`, listed by
  `docir query --type decision`. Read them; they explain the deviations below.

### The shared-index baseline (read before touching persistence)

`docir` keeps a **single shared SQLite schema and one `UnitOfWork`** spanning all three contexts, so
a file write and its metadata/FTS/relation update commit atomically. A strict reading of the rules
(§5.1/§5.3, one owner per table, no shared transaction) would forbid that; going fully compliant
means per-module storage plus an event bus, which is a rewrite the project deliberately deferred
(**adr-d3e3616400bf**). The consequences you will see:

- The repositories, unit-of-work, models, and file stores live in `platform/persistence` and
  `platform/filesystem`, and they map each context's domain entities — so `platform → *.domain`
  edges exist. These are declared `deprecated = true` in `tach.toml`: they are the **ratchet
  baseline** (§8.1/§12.1), reported on every run, allowed only to shrink.
- **Do not add a new `platform → module` edge, a new cross-module edge, or a `tach-ignore`.** The
  sanctioned responses to a boundary error are: route through the module's `api`, move the shared
  thing into `platform`, or (last resort) merge the modules — never widen a baseline. Shrinking it
  (splitting the index per module behind events) is the only allowed direction and would supersede
  adr-d3e3616400bf.
- All cross-context *data* access goes through `platform` (the shared repos), not through another
  module's code. That is why `tags` imports nothing from `documents` even though tag rename rewrites
  documents — it reaches them via `uow.documents`, keeping the module graph acyclic.

## Invariants worth preserving

These look like cruft and are load-bearing. Each line below is the rule; the *why* — the
measurement behind it, the defect that produced it, the alternative that was tried and
rejected — lives in [`.claude/rules/`](.claude/rules/). Claude Code loads a rule file when it
reads a file the rule's `paths:` frontmatter matches, so the argument arrives with the code it
governs. **Read the matching rule before changing behaviour in that area**: a one-line rule is
enough to stop a wrong edit and never enough to argue with.

**Everywhere.** Raise a typed `DocirError` subclass from `platform/errors`, never a bare
`DocirError` — `entry_points/cli/runner.py` maps its `exit_code` onto the process exit code.

### The document write path — [`.claude/rules/documents-write-path.md`](.claude/rules/documents-write-path.md)

- Ids come from the `id_sequences` counter in **one atomic upsert**, never from scanning files;
  `reindex` restores the counter, and two backstops refuse a create onto a taken id.
- The `disk_diverged` guard covers `--replace-body` only — every other edit composes with an
  out-of-band change, so widening it would fail writes that lose nothing.
- **Only a content edit may move `updated`.** A mechanical rewrite must not, or it launders the
  review clock; `TagService` has no `Clock` for exactly that reason.
- A forced delete strips the edge from every referencing document in the same transaction, and
  does not advance their `updated`.
- `update --type` never re-mints the id, refuses a status the target type lacks rather than
  resetting it, re-validates existing edges, keeps the filename, and is not a content change.

### The document read path — [`.claude/rules/documents-read-path.md`](.claude/rules/documents-read-path.md)

- `query`/`search`/`context` return skeletons with **no body**; only `get` returns one. Do not
  add the body back to a list path — the skeleton is the context-saving contract.
- `get --section` returns exactly the span `--replace-section` overwrites; the two share one end
  boundary, and all three of read/write/chunk take headings from `markdown_headings.scan_headings`.
- `code:` globs are checked for shape on write and for reality only in Tier 1; `--code` matches
  them as **text**, before the limit, never by walking the tree.

### Relations and mentions — [`.claude/rules/relations-and-mentions.md`](.claude/rules/relations-and-mentions.md)

- Two graphs: `related:` is authored and gates merges; **mentions** are derived from prose and
  feed **exactly one** check, `orphan`. Do not feed them to another, and do not make an
  unresolved one a finding.
- `context` has one visibility predicate, used by ranked fusion *and* by expansion; expansion
  follows outgoing edges **and** incoming *successor* edges, successors first.
- `dependency` and `blocking` are two properties, both read from the schema — never a hardcoded
  kind set, which strands every custom kind.

### Validation, check and doctor — [`.claude/rules/checks-and-lint.md`](.claude/rules/checks-and-lint.md)

- Three tiers: Tier 0 is a hard synchronous gate, Tier 1 (`docir check`) is non-blocking
  structural warnings, Tier 2 (`docir lint --deep`) is advisory heuristics. **Never promote a
  heuristic to a hard error**, and never mix the tiers.
- `--strict` gates on `error` only. `orphan` and the schema-shaped warnings must stay warnings —
  promoting one red-builds a *correct* repository, which is how a merge gate gets deleted.
- `docir check --fix` is the only sanctioned recovery path; it repairs only what needs no guess,
  reindexes first, and does not advance `updated`.
- `reindex` is the only writer of `schema_baseline` and `index_build`. Absent means *unknown*,
  never *unchanged*.
- `docir doctor` snapshots the environment **before** it dispatches. CI runs `reindex` ->
  `doctor --strict` -> `check --strict`, in that order.

### Staleness — [`.claude/rules/staleness.md`](.claude/rules/staleness.md)

- Staleness is data (`owner`/`verified` + per-type `review_days`), delivered by **pull** — the
  review queue is a query, and there is no notifier.
- `--stale` is filtered after the query and **before** the limit, because the index stores
  neither the clock nor the cadence.
- `verified_code` digests live in **frontmatter, not the index**, hash contents rather than
  mtimes, and absent always means *unverified*. It stays a warning, and `--fix` must not clear it.

### The schema — [`.claude/rules/schema.md`](.claude/rules/schema.md)

- The schema merges core -> profiles -> inline on every command, so it can change with nothing in
  `git diff` to review; `disable_types:` is the only way it subtracts, and exists for the prefix.
- The loader refuses what it can name at load time: an unsatisfiable `required:` field, a status
  no type declares, a `disable_types:` entry that is unknown or contradicted inline.
- Relation edges are typed; the registry is permissive when empty, and per-type
  `allowed_relations` is a Tier 0 whitelist.
- `docir schema validate` reads the **files**, opens no database, and its exit code does not move.

### Embedding and ranking — [`.claude/rules/embedding-and-ranking.md`](.claude/rules/embedding-and-ranking.md)

- Embeddings are the one deferred, eventually-consistent piece — a content change sets a dirty
  flag and returns. **Do not move embedding onto the synchronous write path.**
- Every `##` section is embedded, because the model reads ~512 tokens and ignores the rest;
  `MAX_CHUNK_CHARS` is *derived* from that window, not chosen.
- `score` is rank-derived and has no absolute meaning; `--min-score` filters `similarity`. Graph
  neighbours are never filtered, and a hit with no `similarity` is kept.
- `fastembed` is the default and a hard dependency; the hashing fallback scores *below* plain
  full-text search. Vectors record their `model_id`, and a foreign one is recomputed, not compared.
- A store may set `embed_model:` in `docs-schema.yaml`; the catalogue is a recommendation, not a
  gate. docir ships **no generative model**, not even as an extra.
- Measure before and after any ranking change — and pick the right benchmark: `benchmarks/run.py`
  is the wrong instrument for chunking, for mentions, and for a model change.

### Persistence — [`.claude/rules/persistence.md`](.claude/rules/persistence.md)

- Alembic owns the schema and `alembic/` must sit beside `engine.py`; the FTS5 table is raw DDL in
  migration `0001`, not an ORM model.
- SQLite foreign keys are enabled **per-connection** by a `PRAGMA` listener; a raw connection
  without it orphans rows.

### The daemon and the transport — [`.claude/rules/daemon-transport.md`](.claude/rules/daemon-transport.md)

- The socket path is derived, short, and lives **outside** `DOCIR_HOME` — a deep home would blow
  the ~104-char `AF_UNIX` limit.
- Connect and reply are timed separately and raise **different** exceptions: a refused connect is
  retried, an unanswered reply is never resent. Do not collapse either pair.
- The daemon watches `docs/` and reindexes what changes; the watcher and the socket server share
  **one** `SerializingExecutor`, and the watcher swallows its failures on purpose.
- The daemon is disposable and respawned by the client. Its pid file records a code stamp, and a
  daemon that does not match the current build is stopped and replaced.

### Store discovery and init — [`.claude/rules/store-init-and-config.md`](.claude/rules/store-init-and-config.md)

- Both home decisions live in `config/settings.py`, side by side. Do not move either into the CLI
  layer — that is how `--home` came to be silently ignored.
- `docir init` is a bootstrap in the composition root, in-process, with no daemon; reach for the
  default schema through `documents.api`, never `documents.infra`.
- `--force` regenerates the `.gitignore` always and the schema only while it is unmodified; a
  customised schema is kept and reported, not refused.

### The agents module — [`.claude/rules/agents-module.md`](.claude/rules/agents-module.md)

- `docir agent install/update` runs in-process, bypassing the daemon and the dispatcher. Installing
  **regenerates** the skill directory: every packaged `.md` this build does not ship is deleted.
- Edit the packaged template, never this repo's installed copies, then run `docir agent update`.
- Two skills, the second opt-in. The `AGENTS.md` block **points at** them and does not contain
  them; a third skill is a template plus a catalogue entry.

### The other entry points

- Every MCP tool is one `Request` through a `RequestExecutor` — one tool per dispatcher command,
  never a second implementation — [`.claude/rules/mcp-server.md`](.claude/rules/mcp-server.md).
- `docir build` regenerates its output directory, so it guards what it is about to delete, and it
  does one `get` per document — [`.claude/rules/publishing.md`](.claude/rules/publishing.md).
- Reads federate, writes never do; peers are read-only, a peer behind this build is skipped rather
  than read, and cross-store ranking sorts on `similarity` —
  [`.claude/rules/federation.md`](.claude/rules/federation.md).
- `docir self upgrade` runs reindex -> `agent update` -> check and must not gain the package
  install; the package half re-execs and refuses to guess at an unrecognised install —
  [`.claude/rules/release-and-upgrade.md`](.claude/rules/release-and-upgrade.md).

## Testing

Central `tests/` tree mirroring the modules (**adr-909fc2a170d0** — a recorded deviation from §9),
hermetic through `conftest.py` (`DOCIR_HOME` in a `tmp_path`, `DOCIR_NO_DAEMON`, a `FixedClock`,
synchronous embeddings). The coverage gate is **90%**.

**Verify a new guard by injecting the bug it claims to catch.** A test that has never failed has
not been shown to work, and where a guard scans a corpus, assert *which* items it found — a count
cannot distinguish "nothing is wrong" from "nothing is checked".

Layout, fixtures, the per-layer seams and the guards that police docir's own prose are in
[`.claude/rules/testing.md`](.claude/rules/testing.md), loaded when you open anything under
`tests/`.

## Shipping a business feature (adr-7d9fbbf976e8)

The gates prove a feature *works*. They cannot prove anybody can find it, and docir's user is
an agent that will never read this repository. So a business feature is not done until an agent
holding **only the installed package** can tell what it is, when to reach for it, and how to
invoke it — including how to obtain any input it needs.

Three surfaces carry that, and all three are part of the change, not a follow-up:

- **The packaged skill** (`modules/agents/infra/templates/skill/`) — what the feature is and
  *when* to reach for it. Edit the template, never `.claude/skills/**`, then run `docir agent
  update` so this repo's own copies match what an adopter installs.
- **The CLI docstring** — *how*, with a worked example. `docir <cmd> --help` is JSON when piped,
  so it is the one surface an agent can parse without guessing; a docstring that describes the
  shape without showing it leaves the agent to invent one.
- **`README.md`** — for the human deciding whether to adopt docir at all.

**And exercise it against this repository's own store, through the daemon (adr-f14682e3f4d6).**
A scratch store is two documents, a fresh index and no daemon; docir's corpus is 170+ documents
with real edges, real staleness, a schema baseline, an index built by a previous version, and a
warm model. The gates cannot see the difference and neither can a unit test. 0.18.0 was fully
green — ruff, ty, vulture, tach, contract-sync, 2834 tests — and running the changed surfaces
against the real corpus found three defects anyway: two CLI flags that reached no MCP tool, a
benchmark figure that had drifted as the corpus grew, and `stale-index-build` behaviour nobody
had watched. Cross the second transport too; the MCP drift existed because every check of that
release ran through the CLI.

**Then verify by use, from the state an adopter is in.** Not by re-reading what you wrote and
judging it sufficient — follow the shipped instructions and run the feature. If a step needs
data (ids, a path, a name), the instructions have to say where that data comes from, and
following them has to produce it.

This is the same rule the testing section states for guards, one level out: a test that has
never failed has not been shown to work, and instructions nobody has followed have not been
shown to be followable. `docir bench` shipped its only worked fixture as
`benchmarks/example_fixture.yaml` — a path the wheel does not contain (213 entries, zero
benchmark files) — and the skill named the fixture's *shape* without showing it or saying where
the ids come from. Both read as complete until somebody followed them with no repo checked out.

## Known rough edges / recorded deviations

Real, documented, not stylistic — don't be surprised, and don't paper over them silently:

- **The shared index/UoW is a deviation, not the target end-state (adr-d3e3616400bf).** `platform` is not a
  pure leaf; the `platform → *.domain` tach edges are the baseline that must only shrink. The
  intended future move is per-module storage fed by domain events, which removes them.
- **No authorization / cross-cutting machinery (adr-90e994d931cc).** `docir` is a single-user local CLI with
  no actors or permissions, so §6/§6.1 are intentionally not instantiated. If it ever grows real
  actors, a cross-cutting concern must be introduced per §6.
- **Tests are centralized, not inside their modules (adr-909fc2a170d0).** The next sanctioned refactor is to
  co-locate them under `src/docir/modules/**`.
- `MaintenanceService` (reindex/check/lint) lives in `documents` and reaches the search/embedding
  index through `indexing.api` and the shared UoW; it is the one genuinely cross-cutting operation,
  which is why it sits in the module that owns the aggregate rather than in its own module.
