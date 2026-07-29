# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **`docir tag rename X X --merge` no longer corrupts the tag registry.** A self-merge
  reported success, deleted the tag, and left every document still carrying it — the exact
  `unknown-tag` state `docir check` reports. Renaming a tag to itself is now rejected.
  Introduced in 0.7.0 by the `--merge` feature, whose tests covered merging two *different*
  tags.

## [0.7.0] - 2026-07-29

Six commands that reported success while doing something else, and the adoption story for a
repository that already has documents. This release closes the last of the material findings
from the project's own gap analysis.

### Upgrade notes

- **`docir check` reports two new warning kinds**, `unknown-tag` and `unknown-status`, for a
  document whose tag is not in the registry or whose status its type does not declare. Both
  mean a file was edited outside the CLI. They are warnings, so `--strict` is unaffected;
  a build gating on `--strict-all` may newly fail on a corpus that carries hand-edits.
- **`docir reindex --changed` now removes documents whose files are gone.** That is the fix,
  but if anything relied on the fast path leaving the index alone, it no longer does.

### Added

- **`docir add --id <id>` adopts an existing id**, so a repository migrating a numbered ADR
  corpus keeps its numbering and its historical cross-references. This is not the bulk
  `import` that was built and rejected: nothing is inferred, you still add one document at a
  time after reading it, and the id is supplied rather than guessed. Refused if the id is
  taken or its prefix does not match the type; the next allocation lands past it. Only
  meaningful for a store using `--id-style sequential`.
- **`docir tag rename old new --merge` consolidates two tags.** Renaming onto an existing
  key was rejected outright, so two tags could never be merged: the only path was
  `tag rm --force` on one — throwing the classification away — and re-tagging by hand.
  Vocabularies drift and need consolidating; the registry could only grow. A document
  carrying both tags ends up with one, and the surviving tag's description is kept. Without
  the flag the refusal stands, since a merge discards a description.
- **`docir check` catches the two Tier 0 rules a hand-edit can bypass.** A tag not in the
  registry and a status the type does not declare both parsed cleanly and passed the checks
  silently — a document stayed queryable by a tag `docir tag list` had never heard of, and a
  status outside its type's state machine stuck with no way back out. The CLI cannot write
  either, so both mean a file was edited outside it. They are reported as `unknown-tag` and
  `unknown-status`, both **warnings**: the document is still readable and its edges still
  resolve. Use `--strict-all` if you want hand-edits to block a merge.
- **`docir update --override` now says which rule it broke.** A forced illegal status
  transition left no trace, so the result was indistinguishable from one that transitioned
  legally. It now warns on stderr, naming the transition and the legal moves from the current
  status, and the JSON carries `forced_transition`. Deliberately *not* written to the file:
  docir has no actors to attribute an override to, and git already records the status change
  — what was missing was the signal, not a record. Passing the flag on a transition that was
  legal anyway does not warn.
- **Writes report which store they landed in, and warn about an accidental global one.**
  In a repository nobody had run `docir init` in, `docir add` fell back to the global
  `~/.docir` and succeeded — and since `path` is relative to the *store*, the output read as
  repo-local while the file went to the user's home directory, ungitted and invisible to
  teammates. Every write now carries `store`, and a stderr warning fires when the global
  fallback happens **inside a git repository** — the one case where it is probably not what
  you meant. Outside a repo, and with `DOCIR_HOME` set, nothing warns.
- **`docir tag rm --force` reports the documents it stripped the tag from**, matching
  `docir delete --force` and `docir tag rename --merge`. A forced removal rewrites other
  people's files and used to say only `removed <key>`.

### Fixed

- **`docir reindex --changed` now removes deleted files from the index.** The removal sweep
  was skipped on the fast path, so a document deleted from the filesystem stayed indexed and
  kept being returned by every read path — `docir get` answered for a file that no longer
  existed — and nothing in `--help` or the README said the two modes differed. Skipping it was
  never what made `--changed` fast: the scan runs in full either way, and what `--changed`
  skips is the re-saving. It still does.
- **`docir reindex` reports files it could not parse.** The scan is best-effort — one bad
  file must not abort the rebuild of the rest — but it reported only what succeeded, so a
  partial rebuild was indistinguishable from a complete one. On a fresh clone, two files on
  disk and one indexed looked like success while the unparseable document was absent from
  every read path. The result now carries `documents_skipped`, and a non-zero count prints a
  warning to stderr pointing at `docir check`.
- **`docir search` fills its `--limit` instead of under-returning.** Closed documents are
  filtered after the index returns (FTS5 does not know a status), and a fixed `limit * 2`
  over-fetch meant a corpus where most top hits are closed came back short — indistinguishable
  from a genuinely small corpus. The candidate pool now widens until the limit is met or the
  index is exhausted.
- **`docir init --force` no longer destroys a customised `docs-schema.yaml`.** One flag
  overwrote the schema and the `.gitignore` together, so re-running `init` to refresh the
  gitignore silently replaced every type, status and cadence you had decided on — the one
  file in the store that cannot be rebuilt from the documents. `--force` now regenerates the
  `.gitignore` and a schema still identical to the generated one; a schema you have edited is
  kept, reported as `schema_preserved` in the JSON, and named in a warning on stderr. Pass
  `--force-schema` to replace it as well.
- **An invalid `docs-schema.yaml` now reports a clean error instead of a traceback.** Every
  command builds its executor, and building it loads the schema — but that happened outside
  the error mapping, so a bad schema escaped as an unhandled `SchemaError` with a raw Python
  traceback and exit 1, while `docir schema validate` reported the same error on the same file
  cleanly with exit 3. All commands now agree. Latent until 0.6.0 (only malformed YAML could
  trip it); routine once a typo'd status name became a load error.
- **A YAML syntax error in `docs-schema.yaml` or `docs/tags.yaml` reports a clean error.**
  A bad indent raised `yaml.ParserError`, which is not a `DocirError`, so it escaped the
  mapping that handles every *semantic* schema error and surfaced as a raw traceback — on
  the two files the docs tell you to edit by hand. Now `SchemaError` / `TagRegistryError`,
  exit 3.
- **`related` frontmatter accepts `target` as well as `to`.** The file format writes
  `{to, kind}` while JSON output emits `{target, kind}`, so anyone reading a result and then
  hand-writing frontmatter reached for the key they had just seen and got "missing a 'to'
  id". Both are accepted now; `to` stays canonical on write, so files do not churn.
- **A no-op `archive`/`unarchive` no longer reports `stale: false` on a stale document.**
  The early return built its result without computing staleness, so `docir get` and
  `docir unarchive` disagreed about the same document.

### Changed

- **`docir context` payloads grew ~5% (428 → 448 tokens on the benchmark corpus)** because
  every ranked hit now carries `similarity`. The cost lands only where the field is set:
  `search` and `query` are unchanged, since their results have no similarity and trimming
  drops it. Retrieval quality is unchanged — recall, precision and MRR are identical to the
  0.4.0 baseline.

### Documentation

- **A "what you may edit by hand" contract**, in the README and the packaged agent guide.
  The rule "never edit markdown directly" was stated for agents and never for humans, while
  the whole design invites hand-editing — git-backed files, and a `reindex` that exists for
  exactly that. The contract is per-field: body and the two YAML files yes; `tags`, `status`,
  `related`, `type` through the CLI (each is a Tier 0 rule a hand-edit bypasses); `id` never;
  `verified` never, because it asserts a human re-read the document and nothing can check
  that. It states its own limits too.


## [0.6.0] - 2026-07-28

Three commands that reported success while doing the wrong thing, and one flag named after
the wrong concept.

### Upgrade note

**A schema with a typo now fails to load.** `docir schema validate` used to accept a status
name no type declared; that check runs on every command, so a store whose `docs-schema.yaml`
has such a typo will refuse to start until it is corrected. The error names the offending
value and lists the declared statuses. This is the point of the change — the typo was already
breaking status transitions, silently — but it turns a latent fault into a loud one on
upgrade.

### Fixed

- **`docir tag rename` and `tag rm --force` no longer reset the staleness clock.** They
  rewrote every referencing document with `updated = today`, and staleness falls back to
  `updated` when a document has no explicit `verified` — so a pure classification edit made
  overdue documents report as freshly reviewed, silently forging the signal `docir check`
  and `query --stale` depend on. They now rewrite the tags and leave the date alone, matching
  `check --fix` and `delete --force`.
- **`docir agent install --agent <unknown>` now fails instead of doing nothing.** A typo'd
  target was silently skipped: `--agent claud` printed `[]`, exited 0 and wrote no files, so
  a once-per-repo onboarding command reported success while leaving the repo's agent
  untaught. It now raises and lists the valid targets, matching `docir init --profiles`.
  `docir agent update` resolves through the same path and is fixed with it.
- **`docir schema validate` now catches a typo'd status name.** A schema declaring
  `statuses: {open: [closd], closed: []}` returned `{"valid":true}`; the typo surfaced much
  later, on the first write, as `invalid transition 'open' -> 'closed'` — naming a status
  that *is* declared and sending the reader to their command rather than to the schema. Any
  status name a type does not declare is now rejected at load time: a transition target, an
  `inactive_statuses` entry, or `default_status` (which was unchecked too, and would have
  failed every `add` of that type). The error lists the declared statuses.

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

[Unreleased]: https://github.com/l0kifs/docir/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/l0kifs/docir/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/l0kifs/docir/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/l0kifs/docir/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/l0kifs/docir/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/l0kifs/docir/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/l0kifs/docir/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/l0kifs/docir/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/l0kifs/docir/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/l0kifs/docir/releases/tag/v0.1.0
