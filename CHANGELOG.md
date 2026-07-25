# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/l0kifs/docir/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/l0kifs/docir/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/l0kifs/docir/releases/tag/v0.1.0
