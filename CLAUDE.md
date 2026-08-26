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
  tach module, and the internals are simply never listed as an allowed dependency of outside code.
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

- **Embeddings are the one deferred, eventually-consistent piece.** A content change sets an
  `embeddings.dirty` flag (persisted, survives a daemon restart) and returns; everything else (file,
  metadata, FTS, relations) is synchronous and current when the command returns. Two scheduler
  implementations back this: `InlineEmbeddingScheduler` (in-process/tests, drains synchronously so
  behaviour is deterministic) and `ThreadedEmbeddingScheduler` (daemon, debounced background thread).
  Anything that needs the vector *now* must flush: `--wait-embeddings` on a write, `docir embed
  --flush`, or a full `docir reindex` — which re-embeds every document it re-saves and reports the
  count as `embeddings_recomputed`. There is no flag for "recompute the vectors too", and
  adr-6a4718fa7a7d records why the one that existed was retired rather than repaired: it skipped
  the rebuild instead of adding to it, so it recomputed exactly those vectors and wrote neither
  the schema baseline nor the build stamp. Do not move embedding onto the synchronous write path.
- **Ids are allocated from the DB counter (`id_sequences`), never by scanning files** — that is what
  keeps parallel agents from minting the same id. The claim only holds because the counter is
  bumped by **one atomic upsert** (`INSERT … ON CONFLICT DO UPDATE … RETURNING`, raw SQL in
  `repositories.next_number`): a read-modify-write in Python let concurrent `--no-daemon` processes
  all read the same value and return it, so N parallel adds minted one id N times. The daemon hid
  this by serializing requests, so it only ever reproduced in the mode tests and CI use. Keep the
  allocation a single statement. The counter is
  **derived state and `reindex` must restore it**: `_restore_id_sequences` raises each prefix to
  `max(numeric suffix on disk) + 1`, monotonically. Without that, a fresh clone (the index is
  gitignored) re-minted a live id on the next `add`, and the older document — still on disk — fell
  out of every read path. Two backstops guard the same invariant: `IdGenerator` skips a candidate
  already indexed, and a create refuses to write when a file already claims the id
  (`DuplicateDocumentIdError`, keyed on the id rather than the path, since the filename carries the
  title slug). `tests/modules/documents/test_merge_safety.py` pins all three. Conversely, `docir
  check`'s duplicate-id detection
  scans the *files* directly (`MaintenanceService._find_duplicate_ids`), because two files sharing an
  id are invisible in the index (it dedupes by primary key). That scan is the merge-into-`main`
  guard; `docir check --strict` exits 1 for CI.
- **Tier 1 findings carry a severity, and `--strict` gates on `error` only.** `ERROR_KINDS`
  (`graph_checks.py`) is `duplicate-id`/`dangling`/`malformed` — the corpus is *broken* — plus
  **`empty-index`**, which earns the severity by a different argument: it means `check` could
  not *look*. The graph half reads the index, so with none built every structural finding is
  silent and `--strict` exits 0 — a merge gate that passes by reading nothing, green on a
  corpus with sixteen dangling edges (issue-87410666c867). The warnings below all red-build a
  *correct* setup; this red-builds one that was never checking anything. It fires only when
  the index is empty **and** files exist (so a fresh `docir init` is silent), and a partially
  behind index stays `docir doctor`'s `index-behind-files` warning. The comparison lives in
  `index_is_empty`, shared by `check` and `doctor`, so the two cannot disagree about whether
  a store is readable.
  Everything else (`orphan`, `cycle`, `layering`, `stale`, `unblocked`, `unmatched-code`, `tag-key-format`,
  the three `unknown-type`/`unknown-status`/`unknown-tag`, plus `unknown-relation-kind`,
  `missing-required` and `schema-drift`) is
  a `warning` about shape or age. This is load-bearing: `orphan` fires for every document with no relations — the
  default state of a new one — so a fail-on-any-finding gate went red on a healthy corpus, and the
  only way to keep CI green was to drop the gate, which also dropped duplicate-id detection.
  `CheckIssue` derives `severity` from `kind` in `__post_init__`, so a new check classifies itself
  by being added to `ERROR_KINDS` or not. `--strict-all` restores fail-on-anything.
  **The last three carry a sharper version of the same argument and must not be promoted**: the
  schema they measure against ships in the *package* (the core and the profiles are merged in on
  every command), so a corpus that passed yesterday can fail today with no commit to point at.
  An error kind there red-builds every repo on the release that moved the rule, and nothing about
  the documents changed.
- **A document's `code` globs are validated for shape on write and for reality only in Tier 1.**
  Optional `code:` frontmatter names the code a document governs (issue-90aea6d1b891). Tier 0
  refuses an absolute path, a `..` segment, a backslash separator and an empty entry — patterns
  that can never match — but *accepts* one that matches nothing today, because a decision is
  routinely written before the code it decides. `docir check` then reports `unmatched-code` as a
  warning, and only when `Settings.code_root` finds a `.git` above the store: a global
  `~/.docir` has no tree to resolve a repo-relative pattern against, and an unresolved pattern
  (absent from the map handed to `GraphChecker`) means *unknown*, not missing — the same rule
  `similarity` follows. `content_hash` sorts the globs, like tags: the file keeps the author's
  order and the index returns them sorted, and without the sort every reindexed document read as
  hand-edited and `--replace-body` refused a write that loses nothing.
  **`query --code <path>` matches the patterns as text** (`domain/services/code_globs.py`), not
  by walking the tree — the branch that *deletes* a file is exactly when its decisions must be
  re-read, and a filesystem match answers "nothing" there. It is a post-SQL predicate applied
  **before the limit**, sharing one scan loop with `--stale` (`_post_sql_predicate` /
  `_scanned_page`); a document governing a directory governs the files in it, since a miss costs
  an unread decision and a false hit costs a glance. The forward check (`RepositoryCodeMatcher`,
  "does this pattern still name anything") stays `Path.glob`; the two answer different questions
  and only their *grammar* has to agree.
- **There are two relation graphs, and only one of them is authored.** `related:` is typed,
  hand-written and policed by `dangling`/`cycle`/`layering` and the delete guard. **Mentions**
  are derived: `Document.mentioned_ids(prefixes)` scans the body for ids and
  `uow.mentions.replace` stores them (table `mentions`, migration `0008`), rebuilt by
  `reindex`, never written to frontmatter. **Exactly one check reads them — `orphan`** — which
  is the whole point: it fired for every document whose author linked it by writing its id in
  a sentence, and that false positive is half of why `--strict` had to stop failing on
  warnings. Do not feed them to any other check: a cycle nobody wrote is noise, a `dangling`
  *error* on a forward reference gates a merge, and a delete refused because a paragraph
  quotes an id is a corpus nobody can maintain. Load-bearing details: the grammar lives in
  `platform.naming` beside the tag-key rule (adr-289e788719a7) because `DocId` mints what the
  scanner must recognise, and `DocId` now uses it — two copies would let a document be
  addressable by one and invisible to the other. The scan is restricted to the **schema's
  prefixes**, or `sha-1beef` in a sentence about hashing is an edge. `target` carries **no
  foreign key** and resolution is a read-time join, so an ADR naming the issue it will produce
  starts resolving when that issue is written rather than when the ADR is next saved; a
  self-mention is excluded in the entity, where the id is known. Derivation sits in
  `domain`+`application`, not in the repository: `platform.persistence` may not import
  `platform.naming` (tach), and deriving meaning from prose is not a translation of rows.
  `tags` writes documents without recomputing — a rename never touches a body — and
  `test_a_tag_rename_does_not_disturb_it` fails if that stops being true.
  **A peer whose index is older than this build is skipped, not read.** Peers are opened
  read-only and never migrated by us (adr-fb938175f72a), so every table or column a migration
  adds is one some peer will not have — and it had already broken twice: `mentions` (`0008`)
  took down `context`/`get` with `no such table`, and `document_code.digest` (`0007`) took down
  every hydrate, which is `query` too. Through the daemon that surfaced as "daemon closed the
  connection without responding". `peer_status` now compares the peer's `alembic_version`
  against `head_revision()` (`_peer_schema_status`), so **one rule covers every past and future
  migration** — a guard per column worked and had to be remembered, which is the failure mode
  itself. Three properties are load-bearing: an **unknown** revision is from a *newer* docir and
  is **allowed**, because every query names its columns and refusing it would make upgrading one
  repo break every repo that had not (backwards from what this protects); **no** recorded
  revision is skipped, since "cannot say" is not permission; and the skip reuses the existing
  warn-and-carry-on path, so an unreadable peer never fails the caller's own query. The cost is
  deliberate and stated in the message: upgrading docir darkens every peer until each is
  reindexed.
  **An unresolved mention is deliberately not a finding, and that was measured** (adr-e86c5040d626):
  all 47 in this corpus are documentation *examples* (`adr-0007`, `adr-3f9a2b1c7d4e` — the ids
  the architecture documents use to explain the id format), not typos. Ignoring code spans
  makes it worse: 20 of the 47 sit outside code anyway, and 56 **resolved** mentions live only
  inside code spans, so the filter would delete 12% of the working graph. Naming an id without
  linking to it is a correct thing for a document to do. It *is* reported by `lint --deep` as
  `unresolved-mention`, one finding per document — Tier 2 is where opt-in, never-gating noise
  belongs, and "is this a typo?" is a real if low-yield question.
  **`context` expansion follows them, last and both ways, and that was measured before it
  shipped.** `benchmarks/run.py` could not decide it — that corpus allocates ids at load time,
  so its bodies cannot name one and the mention graph is empty there, the same wrong-instrument
  trap as issue-b1a6e57deeec — so `benchmarks/mentions.py` exists, with a corpus whose bodies
  carry `{key}` placeholders substituted after allocation. Result: recall@5 **0.84 -> 0.93**,
  precision 0.33 -> 0.37, MRR unchanged at 0.86, one task of fifteen regressing. **MRR holds
  because of the budget, not because of expansion**: `seed_budget = limit - expand`, so at the
  shipped `expand=2` the top three ranked hits keep their positions — the same sweep shows MRR
  falling to 0.83 at `expand=3`, where only two do. The sweep also found `expand=1` and
  `expand=2` identical on that fixture (0.93/0.37 both), so the shipped default is not
  evidenced *against*, merely not distinguished; do not read 2 as measured-optimal. Authored edges are still ordered first: a `supersedes` is a
  claim about correctness, a citation is a claim about nothing. Two details of that benchmark
  are load-bearing: it mints **sequential** ids (random ones move ranking ties, and the same
  code scored 0.79 and 0.81 on consecutive runs), and it **derives** the prose-vs-authored task
  grouping from the corpus rather than reading a hand-written label — the first version's
  labels were wrong in the direction that flattered the feature, hiding that mentions also
  restore *backwards* reachability for non-successor edges like `refines`.
- **Staleness has two halves: a calendar and evidence.** `verified`/`review_days` answer
  "how long since a human read this"; `verified_code` answers "has the code moved since they
  did". `update --verified` fingerprints what each `code:` glob matched
  (`RepositoryCodeMatcher.fingerprint`, contents + paths, sha256 truncated to 12 hex) and
  `check` recomputes and compares, reporting `code-changed`. Load-bearing details, most of
  them the same rule stated once more: the digests live in **frontmatter, not the index** —
  unlike `schema_baseline` and `index_build`, this is the document's review state, and the
  index is gitignored, so a clone would see nothing (`test_the_evidence_survives_a_rebuilt_index`
  pins it). It hashes **contents, not mtimes or a commit** — a clone, a checkout and a rebase
  all move those without changing a line, and a finding that fires after `git clone` is one
  nobody reads twice; it also means no history is needed. A pattern naming a **directory is
  expanded to the files under it**, because `**` yields directories and the read path already
  resolves `src/auth/**` that way — without it the most natural pattern records nothing and
  says so silently. `.git` is never walked. **Absent means unverified**, never unchanged, in
  all three places it can be absent (no digest recorded, pattern unresolvable, no matcher at
  all), so a global store and a never-verified document report nothing. With **no matcher the
  digests are dropped, not carried forward**: a digest from an older review under a fresh
  `verified` date is the one combination that misreports. It is a **warning and must not be
  promoted** — a branch that edits code before its docs is the ordinary shape of a change, so
  an error kind fails the CI of every correct commit. **Clearing it is a judgement, not a
  rewrite** — read the document against the code as it now stands and stamp `--verified` — so
  `check --fix` leaves it (a repair has nothing to read *with*). The rule is *not* "only a
  human": the writer here is an agent by design, and a signal only a human could emit is one
  nothing would ever emit. What it excludes is verifying **inside the task that moved the
  code**, which certifies its own change and degrades `verified` to "CI is green" — the
  laundering adr-bd7c4f3c5764 guards against, by another door. Whitespace counts (no AST
  normalisation, deliberately: a parser per language, and no answer at all for a language
  without one) — this is where to start if the noise turns out to be real.
- **The stale-write guard covers `--replace-body` only, and that is the rule, not an
  oversight.** `update` computes `disk_diverged` (index `content_hash` vs the file's) and
  consults it in one branch. Every edit is applied to the document *as it is on disk*, so a
  metadata patch or a section edit **composes** with an out-of-band change and cannot destroy
  it; `--replace-body` is the only mode that discards the on-disk body, so it is the only one
  where divergence means data loss. Extending the guard would fail writes that lose nothing —
  `--set-title` refusing because someone fixed a typo by hand. Pinned by
  `TestDiskDivergenceScoping`. Note it is a *divergence* check, not optimistic concurrency
  control: no caller supplies a version token, so it cannot see a competing writer (the daemon
  serializes requests; `--no-daemon` parallel writers have a small unguarded window).
  The variable is `disk_diverged`, not `stale` — in this codebase `stale` means a document
  past its review cadence, a different concept on a different clock.
- **Only a content edit may move `updated`.** Staleness falls back to `updated` when a
  document has no explicit `verified`, so any mechanical rewrite that bumps it launders the
  review clock — the one trust signal the product offers (adr-bd7c4f3c5764). Three write paths rewrite
  documents without touching `updated`: `check --fix`, `delete --force`, and `tag rename` /
  `tag rm --force`. `TagService` therefore has **no `Clock`** — it was injected only to stamp
  the date it must not stamp. Adding a fourth mechanical rewrite? It does not set `updated`.
  (The alternative — measure staleness from `verified` only — is rejected: it makes every
  never-verified document stale from `created`, which is issue-9cb85759076d's failure mode again.)
- **A forced delete compensates for the edges it breaks.** `delete --force` strips the edge
  from every referencing document in the same transaction and returns their ids (the CLI
  prints "unlinked from ..."), so it cannot leave a dangling reference — the pattern
  `tag rm --force` already used for tags. It deliberately does **not** advance those
  documents' `updated` — the same rule `check --fix` and the tag paths follow, because a link
  removed from underneath you is not a re-verification.
  Consequence for tests: `delete --force` can no longer manufacture a dangling
  edge, so the `drop_file_of` fixture builds one the way it really arises — remove the
  target's file as a merge would, then `reindex`.
- **`docir check --fix` (`MaintenanceService.repair`) is the only sanctioned recovery path.**
  Detection without repair forced the user into hand-editing markdown — the one thing thesis #2
  forbids. It repairs exactly what needs no guess: duplicate ids (re-issued; the *oldest* file
  keeps the id, because existing edges were written against it and an edge cannot say which
  document it meant) and dangling edges (dropped). `malformed`/`unknown-type` are deliberately
  left unrepaired and returned in `RepairResult.remaining` — each needs somebody to read the
  file and decide what it should say, and a repair has nothing to read *with*. It reindexes first — id allocation
  consults the index for a free number — and does **not** advance `updated`, since a mechanical
  repair is not a re-verification (that would launder the staleness clock).
- **The schema loader also rejects a `required:` name no document can carry** — the allowed set is
  `REQUIRABLE_FIELDS`, derived from the `Document` dataclass (minus `path`, which the file store
  assigns *after* Tier 0 runs, so requiring it would reject every create). `required` is checked
  with `getattr` on the entity, so an unsatisfiable name used to load fine and then fail every
  write of that type forever, naming the write rather than the schema (issue-e3c4dfad4f7b). The
  paired rule: "empty" in that check covers an empty **collection**, not only a blank string —
  otherwise `required: [tags]` loads, reads as enforced and enforces nothing. `False` stays a
  value, not an absence.
- **The schema loader rejects a status name no type declares** — a transition target, an
  `inactive_statuses` entry, or `default_status`. Without it a typo loaded fine and failed much
  later as `invalid transition 'open' -> 'closed'`, naming a status that *is* declared and
  pointing at the write rather than the schema. A **dead-end check** ("a live status with no
  outgoing transitions") was built and dropped: it fires on 5 of the 15 shipped types
  (`release_note.published`, `postmortem.published`, `experiment.complete`,
  `hypothesis.supported`, `obligation.breached`), all correct terminal states for documents
  that stay live. "Terminal" and "closed" are different properties, and nothing in the schema
  distinguishes an intended dead end from a missing transition — do not rebuild it.
- **Validation is three tiers and mixing them is the documented overengineering trap.** Tier 0 is a
  hard, synchronous compiler-style gate (missing field, bad status/transition, unknown tag/related,
  unknown/disallowed relation kind); Tier 1 (`docir check`) is non-blocking structural graph warnings
  (incl. **staleness**, **unknown-type** and **schema drift**); Tier 2 (`docir lint --deep`) is advisory heuristics (embedding similarity,
  scope creep, oversized sections, ambiguous headings, unqualified section references,
  unresolved mentions, broken `--expr` examples).
  Never promote a heuristic to a hard error.
  **`oversized-section` has no threshold of its own**: it runs `split_body` and reports what came
  out — which section was cut and how many pieces nothing can name — so the number behind it stays
  `MAX_CHUNK_CHARS`, derived from the measured model window. It fires ~100 times on docir's own
  corpus and that is the honest count, not a reason to raise the bar; Tier 2 is opt-in and never
  gates. Do not promote it: a reference table split in half is two half-tables.
- **The schema can change without anyone editing it, and Tier 1 says so (issue-d891ab5501e6).**
  The core and the bundled profiles are YAML strings compiled into `infra/profiles.py` and
  re-merged by `_merge_profiled` on *every* command, so upgrading docir can add a type, make a
  field `required:`, or change a prefix in a store whose `docs-schema.yaml` nobody touched —
  nothing in `git diff` to review. The index therefore records the resolved schema it was last
  rebuilt against (`schema_baseline`, migration `0005`, one row) and `check` reports the
  difference as `schema-drift`, one finding per change. Three rules hold it up:
  **`reindex` is the only writer of that baseline** (it is already the "make derived state agree
  with the sources" verb; an `accept` command would be a ritual whose only effect is silencing a
  report — the argument adr-bd7c4f3c5764 makes about staleness); **absent means unknown, not
  unchanged**, so a store with no baseline reports nothing rather than reporting its whole schema
  as new (an unparseable one reads the same way, since `reindex` overwrites it); and the payload
  is rendered by `domain/services/schema_shape.describe`, which `infra`'s `describe_schema`
  delegates to — the drift check lives in `application`, which may not import `infra`, and a
  second renderer would mean a baseline written in one shape and compared in another.
  `DOCIR_SCHEMA_NOTICE=1` additionally prints the drift on stderr after every command; it is
  emitted **client-side** through the same `RequestExecutor`, because with the daemon the process
  that first loads a changed schema is the daemon, whose stderr is a log nobody reads.
- **`missing-required` is the one Tier 1 finding a hand-edit is not needed to produce.** Its
  siblings (`unknown-type`/`unknown-status`/`unknown-tag`/`unknown-relation-kind`) all mean a file
  was written outside the CLI; this one means the *rule* moved under documents that were valid
  when written. It reads only the type's declared `required_fields` — a core required field is
  what makes a document parse, so an absent one is already `malformed` — and it shares
  `validation.is_absent` with Tier 0 rather than restating "empty", because the two disagreeing
  would let `check` call a document conforming that the next write refuses.
- **The index records which docir built it, and `docir self upgrade` is the command that
  acts on it (adr-31aa7aa60d11).** Migration `0006` adds the one-row `index_build` table,
  written by `reindex` and nothing else — the same single-writer rule the schema baseline
  follows, for the same reason. It is a *separate* table on purpose: the baseline payload is
  diffed line by line and printed, so a version key inside it would render every upgrade as a
  schema change, and the baseline cannot answer this question anyway — it compares schemas, so
  it is silent for a release that changes how documents are *read* (adr-927aa43d9635 rewrote
  every vector without touching a type or a cadence). `stale-index-build` fires on
  **inequality**, not "older than": a downgrade needs the same rebuild. Absent means unknown,
  so a store not rebuilt since the table arrived reports nothing. `self upgrade` runs
  reindex → `agent update` → check in that order (check last, so the findings describe the
  state it left) and **must not gain the package install**: this process is the code that
  would be replaced, so the rebuild after it would stamp the version on its way out. It is a
  `self` group because `docir update <id>` already means "edit a document", and it is not an
  MCP tool — the halves it orchestrates already are.
- **`docir doctor` snapshots the environment *before* it dispatches, and that ordering is
  the whole command (adr-909734bced92).** Every request runs `ensure_running`, which stops a
  daemon serving other code and replaces it, and every container build creates a missing
  index — so a doctor that asked the store first would repair two of the conditions it exists
  to report and then call them clean. `doctor.snapshot()` reads only this process, this
  environment and the filesystem; `try_execute` (not `execute`) then asks the store, because
  "the store will not open" is a *finding* and exiting there prints nothing at the one moment
  the environment half is wanted. Three consequences are load-bearing. The store half is a
  dispatcher command (`store_status`), so the version comparison and the drift diff stay
  implemented once and an agent reaches them over MCP — while the rest is deliberately *not*
  a dispatcher command, since a daemon reporting on its own process makes "is the daemon
  stale?" inexpressible. `documents` / `documents_on_disk` travel as a pair, and split into **two**
  finding kinds: doctor's own dispatch creates the index, so on a fresh clone the second run
  finds an *empty* one where the first found none — `empty-index` is an error for the same
  reason `no-index` is (every read answers nothing), while a partial mismatch stays
  `index-behind-files`, a warning, because one unparseable file would otherwise red-build a
  repo for a condition `check` already reports as `malformed`. Severity is per *kind*, never
  conditional inside one, so a new finding still classifies itself.
  **CI runs `reindex` -> `doctor --strict` -> `check --strict` in that order** (issue below):
  the index is gitignored, so before the rebuild `check` ran over zero documents and printed
  "no structural issues" — `duplicate-id` and `malformed` still fired (file scans), but
  `dangling`, the other half of the merge guard, never did. Measured: a corpus missing one
  linked-to document passed the old gate and produces 16 `dangling` findings under the new one. And the global `~/.docir` is excluded from
  `shadowed-store` — it sits above every store under the user's home directory, so reporting
  it fires the finding on the ordinary correct setup, the `orphan` failure again. The corpus
  is `check`'s question and doctor never walks the graph; a diagnosis costing what `check`
  costs is one nobody runs while something is wrong.
- **The package half of `self upgrade` re-execs, and refuses to guess (adr-a555ee6bc484).**
  The installer runs only where docir owns its environment — a `uv tool` receipt, pipx
  metadata, a `pyvenv.cfg` — and then `os.execv`s `python -m docir` with a hidden
  `--upgraded-from` (which is also the loop guard), because the process that ran the installer
  is the old build and the reindex after it must not be. A checkout or path install
  (PEP 610 `direct_url.json`), an ephemeral `uvx` env, or anything unrecognised gets no
  command and a reason; the store is still resynced. **The test suite is structurally safe
  because it runs from an editable checkout, which detects as `project`** —
  `test_installation.py` asserts exactly that, and it is the guard that keeps a test from
  replacing the environment it runs in. The release check is opt-in
  (`DOCIR_UPDATE_CHECK=1`), fetched by the daemon at most once a day and *only* read by the
  CLI, so no command ever blocks on the network; `latest` absent means nobody has checked,
  never "up to date"; ordering is `packaging`'s PEP 440, since a hand-rolled compare makes
  0.9.0 newer than 0.10.0.
- **Relation edges are typed (adr-599055502f0e).** `related` entries carry a `kind` (`RelatedRef{target,
  kind}`); the on-disk form is a bare id for the default `relates_to` (so pre-typed files round-trip
  unchanged) or a `{to, kind}` mapping. `relations.kind` is a **non-key** column — one kind per
  ordered `(source, target)` pair — added by migration `0002`. The `relation_types` registry is
  **permissive when empty** (schemas predating typed edges accept any kind). Per-type
  `allowed_relations` is a whitelist enforced at Tier 0.
- **Staleness is data, not a heuristic (adr-bd7c4f3c5764).** Optional `owner`/`verified` frontmatter +
  per-type `review_days`; `docir check` emits a Tier 1 `stale` finding and read views carry a `stale`
  flag. `MaintenanceService`/`DocumentService` need a `Clock` for "today". **AST-anchored** staleness
  is intentionally *not* built — human `--verified` is the honest baseline; anchoring is a future
  additive layer. Delivery is **pull, not push**: `query --owner X --stale` is the review queue and
  `--verified` clears an entry; there is no notifier or scheduler, because an automated nag a bot
  can clear is not somebody vouching for content (the same argument as the detection side).
  `--owner` is a SQL predicate on `DocumentFilter`; **`stale` deliberately is not** — it derives
  from the clock and the type's cadence, which the index stores neither of, so the service filters
  after the query and **before the limit** (`--stale --limit 10` means ten stale documents, not the
  stale ones among the first ten).
- **`score` is rank-derived; `similarity` is the one number with absolute meaning.** RRF
  fuses *ranks*, so `score` says where a document placed and never how good the match was — a
  nonsense query against a one-document store scored the same ~0.0328 a perfect match does,
  which made "nothing relevant exists" inexpressible. `FusedScore.similarity` carries the raw
  cosine through (`fuse` used to compute it, sort by it, and drop it), and `--min-score`
  filters on that. Do not point `--min-score` at `score`. Two exemptions are load-bearing:
  graph neighbours are never filtered (they are there because a selected document links them,
  not because they scored), and a hit with **no** `similarity` is kept — absent means *no
  current vector*, not zero, and dropping it would filter on embedding-queue staleness rather
  than relevance. That is also why `_trim` **rounds** `similarity` instead of dropping a 0.0:
  an absent value must keep meaning "not scored".
- **Read paths return skeletons (two-tier retrieval).** `query`/`search`/`context` return
  `DocumentSummary` (frontmatter + typed edges + staleness, **no body**); only `get` returns the full
  `DocumentView` with the body. Do not add the body back to the list paths — the skeleton is the
  context-saving contract. `get --section "<heading>"` narrows the body to one section and is the
  paired read for chunked ranking (adr-927aa43d9635): it returns exactly the span `--replace-section` would
  overwrite (`extract_section` and `replace_section` share one end boundary — do not let them
  diverge, or an agent can read one span and overwrite another), and an unknown heading raises
  *listing the real ones*, because discovering them by fetching the whole body is the cost the flag
  removes.
  **All three — read, write and chunk — take their headings from one scanner,
  `markdown_headings.scan_headings`, and a heading inside a fenced block is not one**
  (issue-af046a467575). `markdown_sections` used to scan lines naively while `chunking` tracked
  fences, so a document quoting a markdown template read as sections the embedder never saw:
  `--section` returned a fragment ending in an *unclosed* fence, and `--replace-section` ended the
  span at the phantom boundary and stranded the rest of the quote at top level — a corrupted body,
  reported as success. Do not give any of the three its own heading regex; the two agreeing is the
  invariant, and `test_markdown_headings.py` asserts set **equality** against the shared scanner
  because an earlier subset assertion passed with the divergence reintroduced.
- **Every section is embedded, because the model never read the whole body (adr-927aa43d9635).**
  `bge-small-en-v1.5` reads ~512 tokens (~1,900 chars of prose) and silently ignores the rest —
  appending text past it returns a bit-identical vector. 84 of docir's own 103 documents exceed
  that, so 56% of the corpus was absent from the semantic index while FTS5 hid it by covering the
  whole body. `drain_dirty` now writes a document vector **and** one vector per `##` section
  (`chunk_embeddings`, keyed `(doc_id, ordinal)`, migration `0003`), and
  `HybridScorer.semantic_ranking` accepts repeated ids and keeps each document's **best** — RRF
  fuses rankings *of documents*, so the collapse happens before fusion, not after. The collapse
  keeps the winning **candidate**, not just its score: `VectorCandidate` -> `SemanticHit` ->
  `FusedScore.section` -> `DocumentSummary.matched_section` is what tells an agent which heading
  to pass to `get --section` (issue-afd25273ff1f). Absent means *not addressable as a section* —
  the document vector won, the hit was lexical or graph-reached, or the chunk is a preamble or an
  over-long section's continuation — never "nothing matched"; and the field is **not** called
  `section`, because `DocumentView.section` already means "the body was narrowed to this".
  Load-bearing
  details: `MAX_CHUNK_CHARS` (1200) is *derived* from the measured window, not chosen — a chunk that
  overflows it reintroduces the bug one level down, and each chunk carries the title prefix that eats
  into the budget; the splitter tracks fenced code blocks, because a `##` comment inside one is not a
  heading and cutting there yields two invalid chunks; there is **no second dirty flag**, chunks are
  rewritten wholesale under the existing `embeddings` queue in the same transaction; and `lint --deep`
  deliberately still compares *document* vectors only, since chunk vectors would answer "do these
  share a section" rather than "are these the same document". `indexing` may not import `documents`,
  so the entity is the seam: `Document.embedding_chunks()` hands the scheduler positional
  `(ordinal, heading, text)` triples. Coverage on docir's own store went 44% -> 100% (695 chunks);
  recall@5 held at 0.97 while MRR rose 0.94 -> 0.97. Keep the recall gate — max-pooling structurally
  favours documents with more sections.
- **`context` has exactly one visibility predicate, and expansion runs both ways.**
  `DocumentService._is_visible` (archived + inactive status) is called by the ranked fusion loop
  *and* by `_augment_with_related`; do not inline the check into either. They used to differ —
  expansion tested only `archived` — so a `resolved` issue the caller had excluded came back
  through a neighbour edge, and the filter that held on `query`/`search`/ranked `context` leaked
  on the fourth path. Expansion follows outgoing edges **and** incoming *successor* edges,
  successors first in each seed's edge list: a `supersedes` edge points from
  the new document to the old one, so before this the replacement sat one hop away *backwards* and
  the graph could not answer "is this decision still current?" — the question it exists for.
  **`dependency` and `blocking` are two properties, not one (adr-716c2eeb4e51).** `layering`
  asks a structural question — does the source sit above the target — and `unblocked` asks a
  temporal one: does the source wait for it. `depends_on` carries both; `refines` carries only
  the first. Reading `dependency` for both was the shipped behaviour for three days and
  announced a decision refining a *superseded* one as "ready to start", a problem reported as
  good news, latent across 34 edges in this corpus.
  **Which kinds count is schema data, not a hardcoded name set (adr-234b956a48d8).** Traversal
  reads `Schema.successor_relation_kinds()` and layering reads `is_dependency_relation`, so a
  custom kind declared `successor: true` / `dependency: true` behaves like the core ones; the
  frozensets these replaced (`_SUCCESSOR_KINDS`, `graph_checks._DEPENDENCY_KINDS`) are gone, and
  reintroducing one silently strands every custom kind with that shape.
  `DocumentRepository.incoming` takes an optional `kinds` filter
  for this; unfiltered it is still the delete integrity check.
- **The schema is core + profiles (adr-2a3f625bb2f8).** `infra/profiles.py` holds a frozen domain-agnostic
  core (the `decision` type + relation registry + cadences) and bundled profiles (software/research/
  ops/legal). A `docs-schema.yaml` with a `profiles:` key merges `core -> profiles -> inline`; a file
  with no `profiles:` key parses inline-only (fully backward compatible). The default is
  `profiles: [software]`, which resolves to exactly `decision`/`issue`/`architecture`. The core is
  always merged when a `profiles:` key is present (you can't disable it that way); disabling a
  profile after its docs exist leaves them with a type the schema no longer knows — `docir check`
  flags those as `unknown-type`, beside the `schema-drift` finding naming the cause (schema
  resolution does not re-key or migrate existing files — there is no document migration and
  deliberately so: every change class needs somebody to decide, which is what `check --fix`
  already refuses to guess at).
- **Merging only adds, so `disable_types:` is how a schema subtracts (adr-f8cce745d0d5).**
  It is applied *after* core+profiles+inline resolve, and the reason it exists is not the
  name but the **prefix**: `Schema.__post_init__` refuses two types sharing one, so while
  the core declares `decision`/`adr` no other type can claim `adr` — which is exactly what a
  corpus renaming its types while keeping its `adr-...` ids needs (issue-ab138501abfd). The
  unused name staying addable was the second half: two names for one concept, shipped in the
  default schema. Two loader rules hold it up, both the "reported at load, naming what would
  have worked" shape the `required:`/status checks already use: the name must be in the
  resolved set (a typo that silently does nothing forever is the failure mode), and it may
  not be one the same file also declares inline (a contradiction with no reading worth
  guessing). It deliberately does **not** consult the corpus — schema resolution knows
  nothing about documents, and stranding documents on a disabled type is a supported move
  reported as `unknown-type` + `schema-drift`, exactly as disabling a profile already was.
- **`docir schema validate` reports what the schema costs the corpus, and never gates on it
  (issue-3678c897295f).** The command run immediately after a schema edit used to answer only
  "does this file parse?", so it said `valid: true` while a corpus left the type system.
  Four properties are load-bearing. It runs **`GraphChecker.check_schema_conformance`**, which
  `check` also calls — the four findings a *schema* edit can cause; a second list of check
  names is the `is_absent` failure again, one command calling a document conforming that the
  other refuses. It reads the **files, not the index**: a schema edit is a hand edit, which is
  when the index is behind, and a fresh clone has none at all. It opens **no database**, which
  is what preserves `schema validate`'s existing property of being reachable for a store too
  broken to start — do not "simplify" it through `build_container`. And the **exit code does
  not move**: the file is valid and the documents are what changed, so gating here would
  red-build every repo mid-migration — the state a correct migration passes through. The graph
  findings are deliberately excluded: `orphan` fires for every unlinked document, which would
  bury the answer under the default state of a healthy corpus. `affected` counts distinct
  documents, not findings — summing per-kind counts printed "14 of 8 document(s)".
- **`update --type` retypes a document, and every rule about it is load-bearing
  (adr-f8cce745d0d5).** **The id is never re-minted**, prefix included: it is the corpus's
  only address, spelled out in every `related` edge pointing at the document, so a prefix
  records which type *minted* an id and never which type owns it now. Status is validated
  for **membership in the target type**, not as a transition (the type being left has no
  transition graph reaching a different type's), and a status the new type does not declare
  is **refused, not reset** — falling back to `default_status` rewrites every `accepted` in a
  corpus to `draft` and reports success. The existing edges are re-validated against the new
  type even when the call does not supply them, since `allowed_relations` belongs to the
  *source* type and this write persists them. The file moves (`DocumentFileStore.relocate`)
  keeping its **filename** — a retype is not a retitle — and the vacated directory is pruned,
  because `ls docs/` is how a person reads which types a store uses. It is **not** a content
  change: `type` is in `content_hash` but not `embedding_text`, so a corpus-wide rename must
  not queue every document for re-embedding (pinned in `test_embedding_triggers.py`, where
  the recording scheduler makes the decision observable — the inline scheduler drains before
  anything can see it, so an assertion through `embed_flush` passes either way).
  **The source type is never looked up, and that is what keeps the two halves from
  deadlocking**: declaring the replacement type is impossible while the old one holds the
  prefix, and disabling the old one first strands the corpus on an unknown type, so a retype
  that required a known source type would leave hand-editing as the only way through.
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
- **Reaching the socket and waiting for the reply are timed separately, and only one of them
  is retryable.** `_CONNECT_TIMEOUT` (5s, `platform/transport/client.py`) covers the connect;
  a local `AF_UNIX` connect succeeds at once or not at all. The reply is covered by
  `settings.request_timeout` (300s, `DOCIR_REQUEST_TIMEOUT`), because it only arrives after
  the daemon has done the work and one request can be a whole `reindex`. One shared timeout
  meant every command slower than 5s failed while the daemon completed it — `reindex` over
  65 documents takes ~10s. The two failures are then **different exceptions on purpose**: a
  refused connect is a `DaemonError`, the request never landed, and `SocketExecutor` respawns
  and resends it; an unanswered reply is a `DaemonTimeoutError` and is **never** resent,
  because the daemon still has it and the old blanket retry killed it mid-transaction and ran
  the command twice (for `add`, a second document). Do not collapse either pair back together.
- **The daemon watches `docs/` and reindexes what changes, and both halves of that
  are load-bearing.** Hand-editing is *permitted* (the README's by-hand table), so the
  window between an edit and a `reindex` was one where every read answered from a stale
  index and nothing said so. It is safe to automate only because the files are canonical:
  `reindex` writes no markdown, so it can only make the index agree with them — which is
  why it defaults on (`DOCIR_WATCH=0` opts out) rather than being a flag. Two details are
  easy to undo by accident: the watcher and the socket server share **one**
  `SerializingExecutor`, wrapped once in `_run_server`, because the server serializes
  clients but the watcher is a second writer and SQLite has one — two wrappers would each
  be internally consistent and collectively useless. And `DocsWatcher._reindex` swallows
  failures on purpose: a half-written file is normal (editors save in two steps) and the
  next batch fixes it, while an exception would end the thread silently, leaving a daemon
  that looks healthy and has stopped watching. `is_document` includes `tags.yaml`, which
  is canonical and hand-editable but not markdown; filtering on `.md` alone leaves a
  renamed tag unindexed while every document that used it reindexes fine.
- **The daemon is disposable and respawned** by the client (`entry_points/daemon/lifecycle.py`); it
  self-shuts-down after an idle timeout. It is spawned as a detached `python -m docir daemon serve`,
  so `src/docir/__main__.py → entry_points.cli.app:main` and the hidden `daemon serve` command must
  keep working. `daemon serve` builds a container with `background_embeddings=True`.
- **The pid file records a code stamp, and a daemon that does not match is replaced.** A
  daemon loads docir once and lives on, so after an upgrade or an edit to `src/` it kept
  answering from the old code — and a stale answer imitates a correct one (`docir check`
  reported 117 cycles while `--no-daemon` reported 0). `CodeStamp` is `__version__` **plus the
  newest mtime across the package's `.py` files**; the version alone cannot see a source edit,
  since nothing bumps it between commits. `ensure_running` stops and respawns on a mismatch.
  Two details are load-bearing: `current_stamp()` is `@cache`d, because the daemon must report
  the build it *started with*, not what is on disk now; and `stop()` waits for the process to
  exit, because its teardown clears the pid file and unlinks the socket, which a
  freshly-spawned replacement would otherwise lose. A bare-integer pid file (written before
  the stamp existed) reads as an unknown build, which never matches — correctly, that daemon
  predates the check.
- **`init --force` treats the two files it writes as unequal.** The `.gitignore` is a constant
  `composition.py` generates, so regenerating it costs nothing; `docs-schema.yaml` holds every
  type, status and cadence a person decided on and **cannot be rebuilt from the documents**.
  So `--force` rewrites the schema only while it is still byte-identical to the generated one;
  a customised schema is *kept* (not refused), reported as `schema_preserved` and warned about
  on stderr, and replacing it needs `--force-schema`. Skipping rather than raising is
  deliberate: an exception aborts before the `.gitignore` is written, which is the thing the
  user ran the command for.
- **Both home decisions live in `config/settings.py`.** `Settings.resolve` finds an *existing*
  store (flag → env → discovered `.docir` → global); `new_store_home` picks where `init`
  *creates* one (`--home` names the store directly, a positional directory means
  `<dir>/.docir`, both is an error). They sit side by side and cross-reference each other
  because `init` used to compute its own home in the CLI layer, silently ignored `--home`,
  and so escaped every review that traced `resolve`. Do not move either out.
- **`docir init` scopes a repo to a project-local `.docir/` store (adr-20eec6e2e2ca).** It is a bootstrap
  operation in the composition root (`initialize_store`), run in-process by a thin CLI command (no
  daemon/dispatcher). It writes `docs-schema.yaml` + a `.gitignore` for the derived index and runs
  migrations via the normal startup path. `Settings.resolve` discovers the store by walking up for
  `.docir/` (`config/settings.discover_project_home`), so the commit story is `.docir/docs/` +
  `docs-schema.yaml` committed, index gitignored. Do not reach into `documents.infra` for the schema —
  `DEFAULT_SCHEMA_YAML`/`PROFILE_NAMES` are exported from `documents.api`.
- **`docir agent install/update` bypasses the daemon/dispatcher on purpose (adr-3a2d5ee7bc84).** The
  `agents` module installs AI-assistant instruction files (a Claude skill, and an `AGENTS.md`
  block linking it) from one packaged template *directory*
  (`modules/agents/infra/templates/skill/` — `SKILL.md` plus the `reference/*.md` it links,
  the canonical guide; edit it there, not `docs/AGENT_GUIDE.md`, which is now a pointer).
  Installing a skill **regenerates** that directory: every packaged file is written and every
  `.md` under it this build does not ship is deleted and reported (adr-e18250eb3081), because a
  reference file a release renamed would stay on disk, linked from nothing, and still answer.
  The entry point is held under 500 lines by a test — past that, an assistant pays the whole
  guide to learn one command. It touches
  no index/DB, so the CLI builds the service directly via
  `agents.api.build_agent_service(__version__)` and runs it in-process — like `version` and
  `daemon serve`, not through the `RequestExecutor`/`Dispatcher`. Generated files carry a
  `<!-- docir:vX -->` stamp so `update` reports a version transition; a foreign `AGENTS.md` is
  never rewritten (only docir's marker block is).
- **There are two skills, and the second is opt-in (adr-735ba7f6209b).** `claude` teaches the CLI;
  `claude-writing` (`.claude/skills/docir-writing/SKILL.md`, template `writing.md`) teaches how to
  write the documents — one name per concept, one purpose per document, state each fact once and
  link it, and keep each `##` section under ~1,200 chars. That last number is `MAX_CHUNK_CHARS`,
  not a style preference; the skill deliberately carries **no word limit**, because the
  topic-based standards reject one and `similarity_lint.py` already warns on size. It stays out
  of `DEFAULT_AGENTS` since both skills match the same work and a repo that did not ask for the
  second should not pay its context. `TemplateProvider.template(name)` is a keyed catalogue, so a
  third skill is a template plus a catalogue entry — do not grow either skill into a grab-bag.
- **The `AGENTS.md` block points at the skills; it does not contain them (adr-6ed847e02fe5).** It
  carries the template's frontmatter `description` verbatim plus a repo-relative link, so docir's
  own output stops being the duplication docir exists to prevent — and a second skill costs a line
  rather than another ~500. It indexes every skill installed under the same root, and installing a
  skill refreshes an installed block in the same run — so the optional skill is listed once it
  exists without the index dragging it in.
  Three details hold it up. `AgentTarget.points_to` is the block's *floor* —
  content and install dependency both — so selecting `agents` writes the skill too (on `update` as
  well, which is what heals a block whose skill was deleted) and the two cannot disagree. The path
  comes from `posix_path`, never `os.sep`, because the block is committed and read on every OS.
  And a legacy block is identified by the *absence* of `MARK_POINTER`, not by matching the old
  guide's wording — which would rot the moment the template changed.
- **`docir mcp serve` is a third client of the dispatcher, not a second implementation
  (adr-354a4270ecd8).** Every tool in `entry_points/mcp/server.py` is one `Request` through a
  `RequestExecutor` — the same boundary the CLI and the daemon socket cross — so an MCP tool
  and its CLI command cannot answer differently. Exactly one tool per dispatcher command
  (`ping` excepted: a liveness probe, not a document operation) plus `docir_schema`, which is
  the one thing an agent needs that is not a command. `test_mcp_server.py` asserts the
  exposed tool **names** against `Dispatcher._handlers`, so a new command that reaches only
  the CLI fails the build; the names are prefixed (`docir_context`) because the CLI's are
  generic verbs that collide in a client's tool list, and renaming one breaks saved prompts.
  Results go through the same `trim` as the piped CLI JSON — that is why it lives in
  `entry_points/payload.py` rather than in `cli/rendering.py`. `fastmcp` is a **default
  dependency**, not an extra: an agent that only speaks MCP cannot be told to install one.
  `server.py` imports it at module scope and `cmds.py` imports `server` *inside* the command —
  keep that lazy, it is ~0.3s of import that no other command should pay.
- **`docir build` regenerates its output directory, and that is why it guards it.** The site
  is derived like the index, so every `*.html` is removed before writing — a document deleted
  from the store must not survive as an orphaned page nobody can reach and nobody knows is
  stale. "Delete everything here first" has to be sure it owns "here": a previous build leaves
  `.docir-site`, and anything else non-empty is refused unless `--force`, because `--out` is a
  path a person types. The build does one `query` then one `get` per document — bodies are
  absent from every list path by contract (the skeleton rule), so a build that stopped at
  `query` would report the right count and publish empty pages, which looks exactly like
  success. `test_e2e_build.py::test_bodies_reach_the_pages` pins that.
- **Reads federate; writes never do (adr-fb938175f72a).** `.docir/stores.yaml` declares peer
  stores, and `FEDERATED_COMMANDS` (`entry_points/federation.py`) is exactly
  `get`/`query`/`search`/`context` — asserted against `Dispatcher.commands` in the suite, so a
  new command joins by decision rather than by omission. Three details are load-bearing. Peers
  are opened `mode=ro`, which is why they get their own construction path: `build_container`
  runs migrations and creates directories, and a peer is another repository. An unreadable peer
  is skipped with a stderr warning (`peer_status`, called by both the CLI and the fan-out, so
  the two cannot disagree) — a peer's index is gitignored, so a fresh clone of it has none, and
  failing the read would make that everyone's outage. And `merge_ranked` sorts on `similarity`,
  never `score`: RRF ranks *within one store*, so cross-store scores compare corpus sizes rather
  than relevance. Rows carry `store` only while federating — the field is pure cost with one
  store, which is why the read paths never carried it before.
- **All exceptions live in `platform/errors`.** `DocirError` is the base and carries an `exit_code`;
  `entry_points/cli/runner.py` maps that onto the process exit code. Raise a typed subclass, not a
  bare `DocirError`, so the CLI reports the right code.
- **`fastembed` is the default embedder and a hard dependency; the hashing one is the
  fallback (adr-ab9c454b760c).** It was optional, which meant the shipped default scored *shared vocabulary*
  rather than meaning — `DeterministicEmbedder` is signed feature hashing, the same signal
  FTS5 already provides, and two paraphrases with no words in common score 0.0. Measured
  (`benchmarks/`, 2026-07-27 re-based corpus — compare only against figures from that run):
  isolate the embedding signal with `--expand 0` and the hashing embedder scores recall@5
  **0.80, below the 0.83 plain `search` manages on its own**, while the model scores 0.87.
  Full `context` is 0.96/MRR 0.95 with the model against 0.93/MRR 0.80 without.
  Quote the `--expand 0` pair when arguing about embedders: full `context` numbers include
  graph expansion, which lifts both and hides the difference. `DOCIR_EMBEDDER=deterministic`
  selects the fallback — **the test fixtures set this**, so the suite stays hermetic and most
  of it never touches a model. `platform/embedding/fastembed.py` is **no longer excluded from
  `ty` or omitted from coverage**: it is what every default install runs, so a break there
  reaches every user, and lifting the `ty` exclusion immediately surfaced a real diagnostic
  (the adapter held its model as bare `object`; it now depends on a `_TextEmbedding` Protocol).
  Tests that load the real model are marked `slow` (~4 s cold, ~2 ms warm); CI caches
  `~/.cache/fastembed`. Run `uv run python benchmarks/run.py` before and after touching ranking.
  **For a change to the *chunking* rules `run.py` is the wrong instrument**: its corpus has no
  section over the ceiling and none quoting a fenced heading, so a broken splitter scores what a
  working one does (issue-b1a6e57deeec). `benchmarks/chunking.py` is the one that moves. Its
  corpus **declares** each body's real headings by hand — a scanner checked against itself agrees
  with itself, which is why the first version of that guard saw nothing — and it reports structure
  (headings addressable, phantom headings) as the gate with retrieval as context, because which
  section wins a query is the embedder's judgement and tuning prose until it matches would measure
  the tuning.
- **A store may name its embedding model, and `run.py` is the wrong instrument for that
  too (issue-a24f404dd106).** A top-level `embed_model:` key in `docs-schema.yaml` — beside
  `id_style`, which is the precedent for a store-wide policy that is not a type concept —
  selects any model `fastembed` supports. It lives in the committed file rather than an env
  var because the index is gitignored: two clones holding different models would each
  re-embed the corpus behind the other. **The catalogue
  (`platform/embedding/catalogue.py`) is a recommendation, not a gate**: a name docir has
  measured passes silently *and without importing fastembed at all* — that import is most
  of a cold start and the schema loads on every command, so the short-circuit is load-bearing
  and `test_embed_model.py` asserts the model list was never consulted, not merely that
  nothing warned. Any other supported name is accepted with one warning, because a hardcoded
  tuple is worse placed to choose than somebody writing in a language docir never
  benchmarked; only a name fastembed does not know is refused. `verify_embed_model` is
  called by **both** `_build_embedder` and `validate_schema` — `schema validate` is the
  command run right after editing the key, and two checkers would disagree — and it lives in
  the composition root rather than in `Schema`, since answering costs that import and the
  domain must stay pure. The key is **absent from `schema_shape.describe`**, so a deliberate
  switch is not reported as `schema-drift`: drift exists to report what `git diff` cannot
  show you. `docir self status` reports the model in force, because nothing else did.
  **For a change of model `run.py` measures the wrong corpus** — it is in English, where the
  multilingual models lose ranking and buy nothing, which is why the default did not move.
  `benchmarks/multilingual.py` is the one that moves: `corpus.yaml` translated with
  identical keys, edges and judgments, so language is the only variable. Russian paraphrased
  recall goes **0.50 -> 0.80** and MRR 0.63 -> 0.90; the default's *same-words* 1.00 beside
  its paraphrased 0.50 is FTS5 carrying the lexical half unaided, which is what "no better
  than full-text search" means as a number.
- **docir generates nothing, and that is a decision rather than an omission
  (adr-27c63ad02695).** No generative model, not as a dependency and not as an extra. The
  reason is not install weight: docir's caller *is* a frontier model that has read the code,
  so a 0.5-1.5B quantized rewriter underneath it would be guessing at context the caller had
  and did not send. Two mechanisms that would have needed one are already closed by
  measurement — cross-encoder reranking (adr-d657a09b8c4a) and pseudo-relevance feedback
  (adr-46b69a581c65, which cost 0.13 recall@5 on this corpus because the first pass is already
  right 88% of the time). What replaces HyDE is **accepting** it: several caller-supplied
  query strings fused in one `context` call, which needs no model and uses a better one. That
  is unbuilt and ships like any ranking change — measured with `docir bench` first.
- **Vectors record which model produced them, and mismatches are recomputed, not compared
  (adr-ab9c454b760c).**
  `set_vector` writes `embeddings.model_id`; `active_vectors(model_id)` returns only matching
  rows and `dirty_ids(model_id)` treats a foreign or NULL `model_id` as dirty. Without this,
  changing embedder made `docir context` raise `dimension mismatch: 256 != 384` in every
  existing store — different models have different widths, and `Embedding.cosine_similarity`
  refuses rather than silently truncating. The recompute happens on the next write or
  `docir embed --flush`, so the first read after a switch has no semantic signal.

## Testing

Central `tests/` tree, organized to mirror the modules (**adr-909fc2a170d0** — tests are not yet co-located
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
- **Verify a new guard by injecting the bug it claims to catch.** Four defects here survived
  because a test asserted the existing behaviour was intended (`test_check_strict_gates_ci`
  pinned the unusable CI gate; `test_layering_violation` pinned the false positive), or because
  the test silently checked nothing — `test_agent_guide_matches_cli.py` reported 28 valid
  invocations while its regex, thrown off by ``` fences, was not extracting the one line it
  exists to catch. Each was found by running the tool as a user would, never by reading the
  suite. A test that has never failed has not been shown to work. Where a guard scans a
  corpus, also assert *which* items it found: a count cannot distinguish "nothing is wrong"
  from "nothing is checked".
- **`tests/entry_points/test_agent_guide_matches_cli.py` validates docir's own prose**
  against the Typer command tree, introspected from `cli.app` rather than shelled out. Six
  sources: the packaged guide (every file of `modules/agents/infra/templates/skill/`, joined —
  a command moved into `reference/` has not stopped being documented) and `README.md`,
  which an *adopter* reads; `CLAUDE.md` and every file in `.docir/docs/**`, which an agent
  working in this repo reads; every docstring under `src/`, which 37 stale invocations
  survived in after the markdown side was clean; and the six `CONTRACT.md` files, which
  §8.6 forces to change whenever a module's public surface does — so they are the prose
  most likely to name a command on the day it moves. Any `docir ...` in a fenced block, an
  inline code span or an RST literal must resolve to a real command with real flags — so
  prose naming a command that does not exist must not be written in backticks. Three things are deliberate. A retired binary name
  gets its **own** check (`_RETIRED_BINARIES`), because a code span opening with the old name
  instead of `docir ` never reaches the extractor at all — that is how the architecture
  document reached 96 of them. (Naming one in prose here trips that check, which is why this
  sentence describes it instead of quoting it.) `_DELIBERATELY_UNREAL` exempts prose that names a verb *because it does
  not exist* (`docir import`, `docir repair`, `docir schema accept`), and every entry must
  still match something, so a shipped command cannot leave its exemption behind to shadow the
  real thing. And `--type`/`--status` **values** are checked against the core merged with
  *every* bundled profile (`TYPE_STATUSES`), not this store's resolved schema — whether
  `decision` has an `open` status is not a local choice, but which profiles are enabled is,
  so an example may name a `test_plan`. Resolving a command proves only its shape: a
  `--type decision --status open` filter parses, runs, and matches nothing forever.
- The coverage gate is **90%** (`--cov-fail-under=90`); `alembic/` and `fastembed.py` are omitted.

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
