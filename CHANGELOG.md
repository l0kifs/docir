# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-07-26

A `qa` schema profile, schema introspection commands, and the documentation an agent needs
to extend a schema without reading docir's source.

### Added

- **`qa` schema profile** (`test_plan`, `test_case`) and a **`release_note` type** in the
  `software` profile (ADR-0010). Both are additive — existing documents are unaffected.
- **`docir schema show` / `docir schema validate`.** Print the fully merged schema (core +
  profiles + inline overrides — what validation actually enforces, unlike the raw file), and
  check `docs-schema.yaml` before an edit reaches a write. Both run in-process, bypassing the
  daemon, so a schema too broken to start the store can still be diagnosed.
- **A worked, commented-out `types:` / `relation_types:` example in the generated
  `docs-schema.yaml`**, plus a required/optional key reference in the agent skill. The three
  required keys (`prefix`, `statuses` as a *mapping*, `default_status`), global prefix
  uniqueness, and the `allowed_relations` whitelist trap were previously undocumented, so an
  agent asked to extend the schema had to guess.
- `render_schema_yaml(profiles)` and `describe_schema(schema)` on `documents.api`.

### Fixed

- **`docir init --profiles` could silently write the wrong profiles.** The schema body was
  built by string-replacing the literal `profiles: [software]` in `DEFAULT_SCHEMA_YAML`; if
  that line ever changed the replace would no-op, writing the default profiles while
  reporting the requested ones. The body is now assembled structurally around a generated
  `profiles:` line, so the file and the reported result cannot diverge.
- **`docir version` reported the wrong version.** `__version__` was a hand-maintained
  literal that the 0.1.1 release did not bump, so the CLI (and the `<!-- docir:vX -->` stamp
  on generated agent instructions) reported 0.1.0 while 0.1.1 shipped. It is now read from
  installed package metadata, making `pyproject.toml` the single source of truth.

## [0.1.1] - 2026-07-25

Packaging and README fixes so the PyPI project page renders correctly. No code changes.

### Fixed

- **PyPI project page logo.** The README lockup used a repository-relative image path,
  which PyPI cannot resolve; switched to absolute `raw.githubusercontent.com` URLs so the
  logo renders on both PyPI and GitHub.
- **`python` version badge showed "missing".** Added Python trove `classifiers`
  (`3.12`, `3.13`) so the `shields.io` `pypi/pyversions` badge resolves; also added
  standard audience/topic/license classifiers for PyPI discoverability.

## [0.1.0] - 2026-07-24

Initial public release. `docir` compiles git-backed markdown documents into a derived,
read-optimized SQLite index built for AI coding agents — the files are the source of
truth, the index is a rebuildable compile artifact.

### Added

- **Git-backed store with a derived index.** Markdown files (plus `docs/tags.yaml`) are
  canonical; the SQLite index — metadata, FTS5 full-text, a typed relation graph, and
  semantic embeddings — is a `.gitignore`d compile artifact rebuilt by `docir reindex`.
- **Single CLI write path.** `add`, `update`, `archive`, `unarchive`, and `delete`
  guarantee frontmatter/schema consistency and collision-free id allocation; agents never
  edit markdown directly.
- **Two-tier retrieval.** `context`, `search`, and `query` return body-less skeletons
  (frontmatter + typed edges + staleness); `get` returns the full document. `context`
  fuses lexical (FTS5) and semantic ranking via reciprocal-rank fusion.
- **Token-efficient output for agents.** Rich tables at a TTY, compact trimmed JSON when
  piped (~40% fewer tokens); `--json`, `--pretty`, and `--no-trim` force the mode.
- **Typed relation graph (ADR-0005).** `related` edges carry a kind (`supersedes`,
  `depends_on`, `implements`, …) with per-type allowed-relation whitelists.
- **Staleness as data (ADR-0006).** Optional `owner`/`verified` frontmatter plus per-type
  review cadences; `docir check` reports stale and unknown-type documents.
- **Schema: core + profiles (ADR-0007).** A frozen, domain-agnostic core plus swappable
  profiles (`software`, `research`, `ops`, `legal`), merged `core → profiles → inline`.
- **Project-local store (ADR-0009).** `docir init` scopes docs to a `./.docir` store
  discovered by walking up from the CWD; commit `.docir/docs/` + `docs-schema.yaml`, and
  gitignore the derived index.
- **AI-assistant setup (ADR-0008).** `docir agent install` / `update` write a Claude Code
  skill or an `AGENTS.md` block from a packaged template.
- **Warm local daemon.** Keeps the embedding model warm and serializes writes over a Unix
  socket; the CLI transparently spawns/respawns it and it self-shuts-down when idle.
  `--no-daemon` runs any command in-process.
- **Three-tier validation.** A hard Tier 0 compiler-style gate, non-blocking `docir check`
  structural warnings (`--strict` for CI), and advisory `docir lint --deep` heuristics.
- **Optional ONNX embeddings** via the `embeddings` extra (`DOCIR_EMBEDDER=fastembed`),
  with a deterministic embedder as the hermetic default.
- **Modular DDD architecture** — vertical bounded-context modules (`documents`, `tags`,
  `indexing`, `agents`) over a shared `platform`, with boundaries enforced by `tach` in CI.

[Unreleased]: https://github.com/l0kifs/docir/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/l0kifs/docir/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/l0kifs/docir/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/l0kifs/docir/releases/tag/v0.1.0
