# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **`--include-resolved` is now `--include-inactive`** on `query`, `search` and `context`.
  The flag controls the schema's *inactive statuses* — `superseded`/`rejected` for a
  decision, `deprecated` for architecture, `retired` for a policy — but was named after
  `resolved`, a status only two of the fifteen shipped types have. Someone querying decisions
  had no reason to guess that a flag named `--include-resolved` surfaces superseded ones; the
  wire field was already `include_inactive`. The old spelling still works (hidden,
  undocumented) and prints a deprecation notice to stderr, so captured JSON is unaffected.
- **Hidden options no longer appear in the JSON `--help` output.** `describe_help` filtered
  hidden sub-commands but not hidden options, so a deprecated alias would vanish from the
  human help panel and remain in the machine-readable copy an agent reads.

## [0.5.0] - 2026-07-28

Two things the retrieval and staleness features could not previously express: that nothing
relevant exists, and which documents a given person owes a review on.

### Added

- **`docir query --owner <name>` and `--stale` turn staleness into a worklist.** The staleness
  data was detected and never routed: `owner` was stored and interpolated into a single
  `docir check` message, with no way to ask "what do I own?" or "what of it is overdue?", so a
  stale document stayed stale until someone happened to run `check` and read past the orphan
  warnings. `docir query --owner platform-team --stale` is now one steward's review queue,
  cleared a document at a time with `docir update <id> --verified`. `--stale` is applied
  before `--limit`, so the limit counts overdue documents rather than truncating the set they
  were selected from. No notifier and no scheduler: an automated nag a bot can clear is not a
  human vouching for content.
- **`docir context` can now answer "nothing relevant exists".** Every ranked hit carries a
  `similarity` — the raw cosine against your task — and `--min-score` filters on it. The
  emitted `score` is a reciprocal-rank fusion, so it is rank-derived: against a store holding
  only a Postgres decision, `docir context "how do I bake sourdough bread"` returned it at
  roughly the magnitude a perfect match scores, and an agent had no way to tell context from
  noise. The cosine was already being computed and then discarded. With `--min-score 0.5`
  that query now returns `[]`, while an on-topic one scores 0.90 and survives.
  Two things `--min-score` deliberately does not filter: graph-reached neighbours (present
  because a selected document links them, not because they scored) and hits with no current
  vector, whose `similarity` is absent — that means *unknown*, not zero. Run
  `docir embed --flush` if you need the floor to cover everything. Without `--min-score`,
  behaviour is unchanged.

### Documentation

- **ADR-0011 carries an evidence update.** Its cited benchmark figures predate the corpus
  re-base and no longer reproduce. The decision stands, but the argument now rests on
  `context --expand 0` — which isolates the ranking from graph expansion, and where the
  hashing embedder scores *below* plain `search` rather than merely level with it.

## [0.4.0] - 2026-07-28

`docir context` and `docir check` both change what they return. Every fix here came from
running the tool as a user would and finding it disagreed with what it promised — four of
them were pinned in place by tests that had encoded the defect as intent.

### Added

- **The packaged agent guide is now checked against the CLI.** `docir agent install` copies
  one instruction file into adopting repositories, and nothing verified that the commands in
  it existed — it shipped `docir reindex --all`, a flag that never existed, at the post-merge
  recovery step. A test now resolves every `docir ...` invocation in the guide against the
  CLI's own command tree, so a renamed command or a dropped flag fails in the same commit.

### Fixed

- **`docir delete --force` no longer leaves broken links behind.** It removed the document
  and left every reference to it pointing at nothing, in the canonical files, permanently:
  `docir check` reported it forever, and since Tier 0 validates only the edges supplied in
  the current call, the next `update` re-persisted the dead edge. The forced delete now
  strips the edge from each referencing document in the same transaction — as
  `docir tag rm --force` already did for tags — and names them in its output. Their
  `updated` is deliberately not advanced: having a link removed is not a human
  re-verification.
- **`docir context` no longer returns closed documents through the graph.** The
  inactive-status filter was applied to ranked hits but not to one-hop neighbours, so a
  `resolved` issue linked from a matching decision came back without `--include-resolved`
  — while `docir search` and `docir query` correctly hid it. Ranked and graph-reached
  documents now share one visibility predicate. Pass `--include-resolved` to get closed
  work on either path.
- **`docir check` no longer reports a layering violation for an ordinary link.** The check
  read a dependency from every relation kind except `supersedes`/`contradicts` — including
  `relates_to`, which is what every bare id in `related:` becomes. Linking a decision to the
  issue that motivated it, the pairing in this project's own quickstart, was therefore a
  permanent warning with no way to silence it. Layering is now read only from `depends_on`
  and `refines`. Retype an edge as `<id>:depends_on` to get the check back.
- **`docir context` now reaches the document that supersedes a hit.** Graph expansion
  followed outgoing edges only, and a `supersedes` edge points from the *new* document to
  the old one — so an agent retrieving a superseded decision got no signal that a
  replacement existed, with the edge sitting one hop away backwards. Expansion now also
  follows incoming `supersedes`/`contradicts` edges, and places them first, so a tight
  `--expand` budget is spent on the neighbour that can invalidate the seed.

### Changed

- **`benchmarks/run.py` reports the embedder it actually used.** It printed
  `deterministic (default)` from a hardcoded fallback string; the default became `fastembed`
  in 0.3.0 and the label did not follow, so every run since reported a configuration it had
  not measured. `Container` now exposes the resolved embedder and the harness prints its
  model id.
- **The benchmark corpus is re-based to 23 documents and 14 tasks.** It previously contained
  no `supersedes` edge and no document in an inactive status, so the two graph behaviours
  `docir context` depends on most were unmeasurable — both fixes above moved no number at
  all against the old corpus. It now carries a superseded decision pair and a resolved issue,
  and the loader understands typed `related` edges and a `status_path`. **Figures printed
  before 2026-07-27 are not comparable**; the previous baseline is recorded alongside the new
  one in [`benchmarks/README.md`](benchmarks/README.md). The re-base also moved the evidence
  for making `fastembed` the default: quote `--expand 0` (fallback 0.80 vs `search` 0.83,
  model 0.87), not full `context`, since graph expansion lifts both embedders.

## [0.3.0] - 2026-07-27

Semantic retrieval now works out of the box, and three separate paths that could silently
lose a document are closed. Most of this release came from measuring the product against its
own claims for the first time — the benchmark that made that possible ships in
[`benchmarks/`](benchmarks/).

### Changed

- **Semantic embeddings are on by default** ([ADR-0011](docs/adr/ADR-0011-semantic-embeddings-by-default.md)).
  `fastembed` moves from an optional extra to a required dependency. Previously the shipped
  default was a dependency-free hashing embedder that scores *shared vocabulary* rather than
  meaning — the same signal the full-text index already provides — so both halves of the
  "hybrid" ranking measured the same thing, and `docir context` measured no better than plain
  `docir search` (+0.03 recall@5, −0.03 MRR: noise). With the real model it is +0.11 and
  +0.13. **Cost:** ~240 MB of dependencies and a one-time ~64 MB model download on first use.
  Set `DOCIR_EMBEDDER=deterministic` for the model-free embedder — a documented, tested path
  for CI images, containers and air-gapped hosts.
- **`docir check --strict` gates on errors only.** Findings now carry a severity: `error`
  (`duplicate-id`, `dangling`, `malformed` — the corpus is broken) and `warning` (`orphan`,
  `cycle`, `layering`, `stale`, `unknown-type` — shape or age). `--strict` previously failed
  on *any* finding, and `orphan` fires for every document with no relations, so the advertised
  CI gate went red on a healthy corpus; the only way to keep the build green was to drop the
  gate, which also dropped the duplicate-id detection that was its purpose. `--strict-all`
  restores the old fail-on-anything behaviour.
- **`docir init` defaults to `--id-style random`.** A repository store is shared, and two
  branches minting sequential ids can each allocate `adr-0007` without noticing until the
  merge. Pass `--id-style sequential` for human-friendly numbering. Existing stores are
  untouched: a `docs-schema.yaml` with no `id_style:` key keeps minting exactly what it did.
- **`docir context --limit` is a hard ceiling on the response.** It previously bounded only
  the ranked seed set, and the one-hop graph expansion ran afterwards uncapped — `--limit 3`
  could return 9 documents, against a product whose point is a bounded token budget.

### Added

- **`docir check --fix`** — repairs what needs no guess about intent: re-issues duplicate ids
  (the *oldest* file keeps the id, so existing links stay valid) and drops `related` edges
  pointing at nothing. `malformed` and `unknown-type` are left to a human and reported as
  remaining. Previously `check` could detect four kinds of corrupt state and fix none, so
  recovery meant hand-editing markdown — the one thing the design forbids.
- **`docir context --expand N`** — how many result slots may go to graph-reached documents
  (default 2). Slots the graph does not use are given back to ranked hits.
- **`docir init --id-style {random,sequential}`**, plus a schema-wide `id_style:` key that
  every type inherits unless it declares its own.
- **`benchmarks/`** — 20 documents, 12 tasks with relevance judgments, reporting recall,
  precision, MRR and the payload an agent actually reads, per retrieval strategy. It is a
  measurement, not a test: it prints numbers and exits 0.

### Fixed

- **`docir reindex` did not restore the id counter, so a fresh clone lost a document.** The
  index is gitignored, so a clone rebuilds from files — after which the next `docir add`
  re-issued an id already in use. Two files then claimed it, the index kept one, and the older
  document became unreachable through `get`, `query`, `search` and `context` while its file
  sat untouched on disk. Exit code 0 throughout. The counter is now rebuilt from the ids on
  disk, monotonically.
- **Concurrent `--no-daemon` writes all received the same id.** Six simultaneous `docir add`
  calls returned `adr-0002` six times. The counter was read, incremented in Python and written
  back, so concurrent processes read the same value; it is now a single atomic upsert, and
  `busy_timeout` is set explicitly so a blocked writer waits rather than erroring. The daemon
  had been hiding this by serializing requests — which is the mode the docs credited to the
  counter itself.
- **A crash between the file write and the index commit could duplicate an id.** The counter
  rolled back with the transaction while the file it had already written survived. A create
  now refuses to overwrite a file that already claims the allocated id
  (`DuplicateDocumentIdError`, exit 5) and points at `docir reindex`.
- **`docir context` returned closed documents through graph expansion.** The inactive-status
  filter was enforced on three read paths and skipped on the fourth, so a `resolved` issue
  came back without `--include-resolved`.
- **Changing embedder made `docir context` raise.** Nothing recorded which model produced a
  stored vector, and models differ in width, so comparison raised `dimension mismatch`.
  Vectors now carry a `model_id`; foreign ones fall out of ranking and are recomputed on the
  next write or `docir embed --flush`.
- **The packaged agent guide told agents to run `docir reindex --all`**, which is not a flag —
  at the post-merge recovery step the guide exists to teach.

### Documentation

- The README states which configuration each retrieval claim describes, and what semantic
  search costs in install size and first-run network.
- `docir check --strict` is documented as an error-severity gate; the agent guide covers
  `--fix`, `--expand`, and phrasing `context` queries.

## [0.2.1] - 2026-07-26

Two commands did not honour the "piped stdout means compact JSON" contract that the rest of
the CLI follows. Both mattered most to the agent path, which is the one that captures output.

### Fixed

- **`--help` ignored the JSON output contract.** Every other command emits compact JSON when
  stdout is captured, but `--help` is an *eager* Click parameter: it renders and exits during
  parsing, before the app callback resolves the output mode. An agent capturing `docir --help`
  therefore got a Rich panel in which ~10% of the payload was box-drawing characters. Help is
  now serialized as JSON (command, usage, help, options, sub-commands) at every command level
  when piped, and still renders the Rich panel at a TTY. `--json` / `--pretty` override it as
  they do everywhere else.
- **`docir schema validate` never emitted JSON.** It always rendered human text, and Rich's
  80-column hard wrap broke the store path mid-token, so a captured path was unusable. It now
  respects the JSON/table split like its siblings, and the human path no longer wraps the path.

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

[Unreleased]: https://github.com/l0kifs/docir/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/l0kifs/docir/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/l0kifs/docir/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/l0kifs/docir/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/l0kifs/docir/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/l0kifs/docir/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/l0kifs/docir/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/l0kifs/docir/releases/tag/v0.1.0
