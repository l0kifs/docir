# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.22.0] - 2026-08-30

A store arrived on a machine with its documents and no index, and every read answered
nothing while every write said the document did not exist. Both halves of that are fixed: the
message stops asserting a deletion that never happened, and the state stops occurring, because
opening a store is now what builds it.

### Upgrade notes

- **A fresh clone or `git worktree` no longer needs `docir reindex` before it can be read or
  written.** Opening the store rebuilds an index it finds empty, in about a second on a
  190-document corpus, and leaves the vectors to the background queue. The explicit `reindex`
  is still what computes those vectors, so it stays first in the CI order.
- **`docir doctor`'s `no-index` finding is now a warning rather than an error.** A
  `doctor --strict` that failed on a fresh checkout will start passing — the run reporting the
  finding is one of the things that repairs it. `empty-index` keeps the error severity, for
  the stores that rebuild does not reach.
- **Nothing else changes without you asking.** A store with a built index reads exactly as it
  did.

### Changed

- **Opening a store with no index builds one.** `.docir/docs/` is committed and `index.db` is
  gitignored, so a fresh clone, a new `git worktree` and every CI checkout arrive with the files
  and no projection of them — a state nothing repaired, because the daemon's watcher rebuilds
  what *changes* and an untouched checkout changes nothing. It stayed unusable until somebody
  remembered `docir reindex`, which docir's actual user, an agent, has to be told twice: once
  that the command exists, once to run it and retry.

  It was a manual step on a cost estimate that was wrong. `docir reindex` on this repository's
  191 documents takes ~70s — but ~69s of that is the embedding drain, loading the ONNX model to
  write 1,454 vectors. The rebuild itself is **~0.9s** against a 0.98s baseline `get`. So the
  bootstrap does the rebuild and defers the vectors: every document is left dirty for the queue a
  write already uses, a background scheduler is woken, and `docir doctor` reports what is still
  queued as `embeddings-pending`. Until it drains, `context` ranks on full text and the graph
  alone — a worse answer than a warm store, and an answer, where the state it replaces returned
  nothing at all. `docir reindex` and `docir embed --flush` are still what compute them, which is
  why neither leaves the documented CI order.

  Only the empty case. A store that is merely *behind* is untouched and stays `doctor`'s
  `index-behind-files`, since rebuilding on any disagreement would make opening a store a
  corpus-sized write on every checkout carrying one unparseable file. Peers are never
  bootstrapped: a federated read that rebuilt another repository's index would make a read a
  write in a repository nobody asked us to touch. (adr-e53c813d2f13)

- **`docir doctor`'s `no-index` is now a warning, worded in the past tense.** Doctor's own
  dispatch opens the store, which is what rebuilds it, so the finding names a condition the run
  reporting it has already undone — the treatment `stale-daemon` already gets. An error there
  fails `--strict` on a store that is now fine. `empty-index` keeps the error severity: an index
  holding nothing beside files is one the bootstrap did not reach, so every read still answers
  nothing.

### Fixed

- **`no document with id '<id>'` no longer denies a document that is sitting on disk.** The
  index is derived and gitignored, so a fresh clone and every new `git worktree` start without
  one — and nothing on the read or write path builds it, the daemon's watcher included, since
  it rebuilds what *changes* and an untouched checkout changes nothing. `get` and `update` then
  answered a miss with a statement about the corpus that was false, which sends a human looking
  for a deletion that never happened and an agent — which cannot glance at `docs/` and see the
  file — to conclude the document is gone. The reporter's automated workflow gave up a document
  amendment to it. The message now names which of the two happened, through the same
  `index_is_empty` comparison `check` and `doctor` have reported as `empty-index` since 0.20.0;
  neither of those runs on the path that hits this, so the diagnosis existed only in the store's
  health report and never where somebody met the symptom. Same `DocumentNotFoundError`, same
  exit code 4, same `no document with id '<id>'` prefix the batch read reports per reference —
  only where the message sends you changes. Reindexing automatically instead was rejected: a
  rebuild is safe, but doing it inside an arbitrary write makes a bounded command corpus-sized
  at the moment somebody is waiting on it. (issue-e5a0cb196607, github issue #7)

## [0.21.0] - 2026-08-29

A federated hit named the repository that answered it and nothing about what that repository
holds — which is the one thing a reader has to know before weighing it. A store now describes
itself, once, and that sentence travels with every row it answers. The second half of the release
is what shipping the first taught: every gate here was green, and the change still broke every
read for anyone still on 0.20.0, because no gate in this repository runs the build people already
have.

### Upgrade notes

- **A `stores.yaml` that describes a store must still declare `stores:` — `[]` when it has no
  peers.** docir 0.20.0 and earlier refuse a file without that key, so a description-only file
  takes `context`, `query`, `search`, `get` and `doctor` down for everyone in the repository who
  has not upgraded, while writes keep working. Every example docir ships spells it that way, and a
  test pins the spelling in the packaged skill, the CLI docstring and this repository's own store.
- **Nothing else changes without you asking.** A store that describes itself nowhere reads exactly
  as it did, field for field.

### Added

- **A store says what it is, and every federated hit carries it.** `description:` in
  `.docir/stores.yaml`, and `store_description` beside `store` on every row that store answers —
  `query`, `search`, `context` and both shapes of `get`. `store` is a path: it separates two hits
  and says nothing about the corpus behind them, while the judgement a reader has to make about a
  hit from another repository is whether that corpus governs what it is doing. `platform`, `core`,
  `shared` are what repositories are called, not what they hold, so an agent either trusts a
  decision with no authority over its task or discounts the one that decides it.

  The store describes *itself* rather than each reader annotating the peers it declares: written
  once by the people who own the corpus, and it is the only spelling that also labels the reader's
  own rows, since a federated read merges local hits with its peers'. Absent, never empty, and a
  single-store read still carries neither field. `docir doctor` prints what this store and each
  declared peer say they are, so a description that never arrives is visible without staging a
  query that happens to hit that corpus. (adr-84fb02d5061b)

### Changed

- **An unrecognised key in `stores.yaml` is judged rather than uniformly refused.** One that
  misspells a key this build knows — `store:`, `stors:`, `desc:` — raises and names what it was
  probably meant to be: it otherwise reads as a store that declared nothing, and the read answers
  locally without saying so. One that resembles nothing here is kept, ignored and reported, by a
  CLI warning and a `stores-file-unknown-key` doctor finding — it is most likely written by a
  *newer* docir, and refusing it would make one repository's upgrade break every repository that
  had not upgraded yet. That is the call `peer_status` already made for a peer's index revision,
  three functions away.

### Fixed

- **A malformed `stores.yaml` printed a stack trace.** It is parsed client-side, before anything is
  dispatched, so it sat outside the boundary that maps a `DocirError` onto an exit code — the third
  half of that gap, after the container build and the transport. `docir doctor`, reading the same
  file through the same function, had been printing the message all along. (issue-06f48d8f239f)
- **Forty parameters rendered as a flag name and a blank column**, across fourteen commands:
  `query --tag`, `add --status`, `update --replace-body`, `embed --flush`, every `doc_id`
  argument. `--help` is the whole discovery surface, and the README sells the CLI as the agent
  contract. The test's oracle is the command tree Click renders from, so a parameter added without
  `help=` now fails in the commit that adds it.
- **Three error paths named the failure and not the fix.** `--body-file` was read unwrapped, so a
  missing path, a directory or a latin-1 draft escaped as a traceback and exit 1 while every other
  bad argument on the same command printed a message and exit 2. `error: unknown error` now points
  at `docir doctor`, and `try_execute`'s fallback names the store it could not open.
- **Twelve slow steps ran with nothing on screen** — `reindex`, `check --fix`, `embed --flush`,
  `doctor --probe`, `self status --refresh`, both halves of `self upgrade`, and the in-process
  executor build, which loads the embedding model and on a cold cache downloads ~67 MB before it
  returns. On stderr, and only when stderr is a terminal: stdout carries the JSON an agent parses,
  and an MCP client reads that stream as its protocol.

### Internal

- **A change is now run against the docir on PyPI before it ships, in both directions.** Every
  gate here runs one build against itself, and a store is a committed artifact read by whatever
  docir each teammate installed and by every repository declaring it a peer — so a change to a
  committed file's shape, the on-disk contract or the index schema is an interface change against
  builds already in the wild. The store description was green on lint, types, tach, vulture, 3,299
  tests, `doctor --strict` and `check --strict` on the real corpus, and both transports, and still
  broke every read on 0.20.0. A refusal is the break; a field an older build cannot show is not.
  (adr-ab4598c6f707)
- **`scripts/check_expressions.py` checks the commands in a release body**, not only its `--expr`
  arguments. A release page is where a flag gets named from memory, and an agent runs a backticked
  line regardless of the sentence around it. The extractor and resolver moved to
  `scripts/cli_oracle.py`, shared with `test_agent_guide_matches_cli.py` — 1687 cases before the
  move, 1687 after. (issue-87a27629f6a6)
- **`publish-to-pypi.yml` was the only workflow still on Node 20.** It runs once per release, at
  the moment a release is already tagged, and `ci.yml` and `pages.yml` had both been bumped. One
  version per action now, rather than one per workflow.
- **Two unused unpackings** that ruff 0.15 reports (RUF059) made `ruff check .` red without a
  commit here; `ruff>=0.9` stays unpinned deliberately.

## [0.20.0] - 2026-08-27

Every gate in this project was green. Four of them were green because they were not looking:
`check --strict` read an index no CI checkout has, the diagram check asserted a file existed
rather than a diagram drawing, the model cache named a directory fastembed stopped writing to,
and a workflow error stopped every job while the YAML parsed fine. This release closes those and
adds the command that reports the whole class — the conditions that produce an answer imitating
a correct one.

### Upgrade notes

- **`docir check` now reports `empty-index`, and it is an error.** A `check --strict` that runs
  on a fresh clone without rebuilding the index first will start failing. It was passing by
  reading nothing: measured here, a corpus with one linked-to document removed produced zero
  findings before a reindex and sixteen `dangling` errors after. Put `docir reindex` in front of
  it — CI now runs reindex -> `doctor --strict` -> `check --strict`. A freshly `docir init`-ed
  store stays silent, since it has no files either.
- **The Claude skill is now a directory, and installing it regenerates that directory.** Every
  packaged file is written and every `.md` under it this build does not ship is **deleted** and
  reported. Hand-edited files under `.claude/skills/docir/` will not survive `docir agent update`
  — the same rule `docir build` applies to `--out`, for the same reason. Run it after upgrading;
  nothing detects a stale skill later.
- **Nothing else changes without you asking.**

### Added

- **`docir doctor` — one report for every way docir is subtly wrong.** A daemon serving code you
  replaced, `DOCIR_EMBEDDER` left over from a test run, an index built by another version or
  behind the files it projects, a schema that moved inside the package, a peer skipped for schema
  skew, writes about to land in the global store. None of these raises; each produces an answer
  that imitates a correct one. Every one was already detected *somewhere* — `daemon status`,
  `self status`, a stderr line during a read, one finding among a hundred in `check` — and none
  was reportable together, which is the property that matters.

  Each finding carries the command that closes it. Severity derives from the kind, so `--strict`
  gates on errors only and the ordinary state of a repo between an upgrade and its next reindex
  does not fail a setup script. No network call, and no model load without `--probe`.

  The environment is snapshotted **before** the first dispatch, which is the whole command:
  dispatching first would replace a stale daemon and create a missing index, then call both
  clean. The store half is a dispatcher command, so an agent reaches it over MCP as
  `docir_store_status`; the process half deliberately is not, since a daemon reporting on itself
  makes "is the daemon stale?" inexpressible. (adr-909734bced92)

- **Batch reads: `docir get` takes several addresses in one request.** An address is `<id>` or
  `<id>#<heading>` — the form a ranked hit hands back as `matched_section`. Roughly half a second
  of a docir read is starting Python and importing docir, while retrieval underneath is flat from
  25 to 2000 documents, so five reads cost five interpreters; over MCP the same shape costs five
  model turns.

  Measured (25 documents, p50 seconds, five bodies): warm daemon 2.506 -> 0.508, cold 3.133 ->
  1.320, `--no-daemon` 4.248 -> 0.872. The floor row is 0.522, so warm, the five reads themselves
  are free.

  An address that does not resolve lands in `missing` beside the documents that did — one deleted
  id must not cost the caller the other four — while a malformed address still raises, because
  that is the caller's own typo. The reply shape follows the payload key, not the result count, so
  the single read is unchanged. `docir build` is rewired onto it. (adr-fe7c91f61f32,
  issue-9509f9fa3631)

- **The packaged skill is a directory, and installing it regenerates the directory.** The CLI
  guide had reached 764 lines / ~11.8k tokens, so every session that triggered the skill paid the
  whole guide to learn how to run `docir context`. It is now a 255-line entry point carrying the
  everyday loop plus six task-grouped files under `reference/` — setup, retrieval, schema,
  maintenance, publishing, troubleshooting — which cost nothing until read. A reference file a
  release renamed no longer stays on disk, linked from nothing, and still answering.
  (adr-e18250eb3081)

### Fixed

- **`docir check --strict` passed by reading nothing.** `.docir/docs/` is committed and the index
  is gitignored, so a CI checkout has no index — and `check`'s graph half reads it. The
  file-scanning half (`duplicate-id`, `malformed`) kept firing, which is why nothing looked
  broken: a half-alive gate is harder to notice than a dead one. `dangling`, the other half of the
  merge-into-`main` guard and the reason the step exists, never fired.

  `empty-index` is an error against this codebase's own rule about promoting warnings, on a
  different argument: every warning it refuses to promote describes something that moved and
  *still answers*, so promoting one red-builds a correct setup. This one describes an index that
  answers nothing. A warning would have changed nothing, which is the test. (adr-1cccd77cb023,
  issue-87410666c867)

- **`docir get <peer-id>` named the wrong repository.** `_emit_document` overwrote a federated
  hit's `store` with the local home.

- **The mermaid guidance named a version docir itself had stopped using.** The skill and README
  told adopters to fetch 10.9.3 on the stated grounds that "mermaid 11 ships only ES modules",
  while `pages.yml` had been publishing with 11.16.1. The claim is false: mermaid 11's package
  `exports` name only `dist/mermaid.core.mjs`, but `dist/mermaid.min.js` is still published and
  assigns `globalThis["mermaid"]`, which is exactly what a plain `<script src>` needs. Verified by
  rendering rather than by reading the bundle. Both surfaces now name the file and the property
  that matters. (issue-28e5dc0191cd)

- **`self upgrade` and `agent update` disagreed about their own JSON.** Each serialized
  `InstalledFile` separately, so the upgrade reported an install without naming the reference
  files it wrote. One serializer now, with a test comparing the two commands' keys.

### Measured and rejected

- **The obvious guard for the empty-index hazard.** Asserting that `check` over an unbuilt index
  reports nothing is `test_check_strict_gates_ci` a second time — the test that pinned an unusable
  CI gate and therefore kept it, one of four defects CLAUDE.md names as surviving because a test
  asserted the existing behaviour was intended. The tests instead pin the *hazard*: a corpus with
  one dangling edge, invisible before a reindex and an error after. Delete the reindex step from a
  workflow and they still pass; read them and you cannot delete it by accident.

### Internal

- **`actionlint` gates the workflows** (`uv run actionlint`). A workflow file is the one thing in
  this repository that cannot be validated by running it — the first honest feedback arrives after
  `main` is already red. A job-level `env:` using the `runner` context is valid YAML and a
  workflow-file error: GitHub rejected the file, zero jobs ran, and the failure said only
  "workflow file issue". It ships as `actionlint-py`, a wheel vendoring the Go binary, so the gate
  runs locally like every other one — which is the point, since a gate that only fires after a
  push cannot stop the push. (issue-b323a5b2ba18)
- **The model cache never hit.** The workflow cached `~/.cache/fastembed`; fastembed 0.8 resolves
  its cache to `tempfile.gettempdir()/fastembed_cache`. Every run re-downloaded ~64 MB while the
  step's comment claimed it was downloading once. Both sides now spell one literal, because a
  job-level `env:` value is not shell-expanded while `actions/cache` *does* expand `~` in `path:`
  — one side expanding and the other not is how they came to name different directories. Cold 8s,
  warm 0.93s. (issue-82b01d7f80d0)
- **`pages.yml` asserts the diagrams draw**, serving the built site in Chromium and requiring an
  `<svg>` with real content, rather than checking that `site/mermaid.min.js` exists. Verified by
  injecting two runtimes the file-exists check could not tell from a working one — a no-op global
  and an ESM-only module.
- **`scripts/check_expressions.py`** compiles every `--expr` in a release body before it is
  published. A release page is the one surface docir's own guards do not reach: it is written
  once, published, and copied from. v0.18.0 shipped `owner == null` and had to be corrected after
  the fact.
- **CLAUDE.md is split into path-scoped `.claude/rules/`**, 942 lines to 356. An imported file is
  expanded into context at launch, so `@path` saves nothing; a rule with `paths:` frontmatter
  loads only when a file it governs is read. Guarded both ways — a glob that matches nothing is a
  rule nobody is ever shown.

## [0.19.0] - 2026-08-25

0.18.0 gave you a grammar to ask questions with. This one lets a store *state a rule* in it —
and then found that a mistyped question had been answering "nothing wrong" all along.

### Upgrade notes

- **`owner == null` now errors, and it always should have.** Bare `null` is an identifier in
  JMESPath, not a literal; the literal is `` `null` ``. The old form compared a key no document
  carries against itself, which is `None == None`, which is the answer you wanted — for the
  wrong reason. Every `--expr` example docir shipped in 0.18.0 used it. Rewrite as
  `` owner == `null` ``; the error names what would have worked.
- **Nothing else changes without you asking.** `checks:` is absent from every existing schema,
  and a store that declares none behaves exactly as before.

### Added

- **A store declares its own checks: `checks:` in `docs-schema.yaml`.** A name, a JMESPath
  expression over the same projection `query --expr` evaluates, and a message. `docir check`
  reports each match as a Tier 1 warning.

  ```yaml
  checks:
    superseded-still-live:
      expr: "length(related_by[?kind=='supersedes']) > `0` && status != 'superseded'"
      message: something supersedes this and it is still in a live status
  ```

  **docir ships none of them.** The grammar is docir's; every rule written in it is yours. That
  is what keeps adr-b2cfed9d5888 intact — it refused docir having opinions about your
  architecture, not your ability to state yours — and a shipped default expression appearing
  here is how it would cross back.

  Three rules hold it up. Always a **warning**: `--strict` gates on docir's own error kinds and
  must mean the same thing in every repository, so `--strict-all` is what makes your rules
  fatal. The name may not collide with a finding docir defines, and the reserved set is *all* of
  them — reserving only the errors would let a store redefine `stale` and leave a reader unable
  to tell whose finding they were reading. And one projection, shared with `query --expr`,
  because a rule is written by trying it as a query first.

  It waited for a rule somebody actually wanted. The one above is docir's own, found two real
  violations on its first run, and went silent once they were retired.

- **`docir lint --deep` reports `broken-expression`.** A `--expr` documented in a body that
  would not run. Tier 2, because a document may quote a deliberately wrong expression to explain
  why it is wrong.

### Fixed

- **An expression naming a field no document carries is refused.** JMESPath evaluates an unknown
  identifier to `null` rather than raising, so `stauts == 'open'` matched nothing, returned an
  empty result, and read exactly like a corpus with nothing wrong — and a *declared* check
  carrying that typo would have run forever, finding nothing, looking like a rule that passes.
  The error names what would have worked.

### Measured and rejected

- **A `code:`-coverage advisory** — flagging a document that describes code and declares no
  glob. On this corpus 63 of 173 documents name a path and declare none; restricted to live
  architecture, decision and reference it drops to seven, and **none of the seven should declare
  one**. The clearest candidate names `src/auth/**` — the *example* it uses to teach the field.
  Prose naming a path is not evidence of governance, and `code:` is a claim, so a false positive
  asks an author to assert something untrue. (adr-f0fb4833ab04)

### Internal

- **Every change is now exercised against docir's own corpus, through the daemon, before it is
  reported done** (adr-f14682e3f4d6). 0.18.0 shipped with every gate green and three defects
  that only a real store with history exposes. A scratch store is two documents and no daemon;
  the difference is what the rule exists for.

## [0.18.0] - 2026-08-25

Retrieval was a black box you could not point at your own corpus, could not see inside, and
could not improve without editing the source. This release opens all three: a model you can
change, an instrument you can run, a trace you can read, and a way to hand docir a better
question. Every ranking change in it was measured before it shipped, and two were measured and
thrown away.

### Upgrade notes

- **Run `docir self upgrade`.** No migrations, but the relation-kind registry gained a property
  and the index records the schema it was built against — until you reindex, `check` reports
  six `schema-drift` findings, one per core kind.
- **Nothing is rewritten and no flag is retired.** `embed_model:` is absent from every existing
  schema, which means the default, so retrieval is byte-identical until you set it.
- **If you publish diagrams**, `--mermaid` now refuses a non-UMD bundle. mermaid 11 stopped
  shipping one; see below.

### Added

- **A store can choose its embedding model: `embed_model:` in `docs-schema.yaml`.**
  The default, `bge-small-en-v1.5`, is English-only, so a corpus written in another language
  retrieved no better than full-text search with nothing to report it. Measured on a Russian
  translation of the benchmark corpus: paraphrased recall@5 **0.50 → 0.80** and MRR 0.63 → 0.90
  with `paraphrase-multilingual-MiniLM-L12-v2`, which is the same 384 width for 220 MB instead
  of 67. On the *English* corpus the same swap costs ranking and buys nothing, which is why the
  default does not move — both halves of the design are evidenced, by different numbers. The
  key lives in the committed schema rather than an environment variable because the index is
  gitignored: two clones holding different models would each re-embed the corpus behind the
  other. Any model `fastembed` supports is accepted; three are measured, and anything else
  warns that docir embeds queries and documents identically, so a model trained on asymmetric
  prefixes will rank below its published numbers. `docir self status` reports the model in
  force. (adr-ab9c454b760c built the machinery; this is the setting it was missing.)

- **`docir bench <fixture.yaml>` — the retrieval instrument, pointed at your corpus.**
  docir published retrieval numbers measured on docir's corpus, which an adopter inherited as a
  claim. A fixture is a list of `{id, task, relevant}` naming document **ids** — not paths, so
  it survives a retitle and a retype. Three rows come back: `context`, `context --expand 0`
  (which removes graph expansion, the thing that lifts every embedder and hides the difference
  between them) and `search`. An id no document carries is reported under `unresolved` and
  excluded rather than dropped quietly, because a shrinking recall denominator *raises* the
  score — a rotting fixture would read as retrieval improving.

- **`--explain` on `context` and `search`.** Where a hit placed in the full-text and vector
  rankings, each RRF term, the raw cosine, the section that matched, and for a graph-reached
  document the seed it came from and whether that edge was a successor, a relation or a
  mention. Keys are omitted rather than nulled: no `lexical_rank` means the full-text index
  never returned it, which is the most useful single fact about a hit that ranked badly.

- **`context --also` — your own phrasings, fused.** docir writes none of them, because the
  caller is already a model that has read the code. Passing a hypothetical *answer* is HyDE
  done by a better model than docir could ship: measured, a correct one takes recall@5 from
  0.88 to **1.00**. Use it when you could defend the answer you are guessing — a confidently
  wrong one costs 0.88 → 0.75, and that asymmetry is documented rather than hidden.

- **`docir query --expr '<JMESPath>'` — the questions the flags cannot ask.** An expression over
  each document's own fields plus its edges **resolved in both directions**, each carrying the
  other document's type and status: `stale && owner == `null``,
  `related[?status=='superseded']`. Applied before `--limit`, so the limit counts matches.
  docir ships **no** expressions of its own — this is the ability to state a rule, not a rule.

- **`docir check` reports `unblocked`: a live document whose every blocker has closed.** The one
  finding that is good news. A `depends_on` edge claims this work waits on that work, and until
  now only `context` expansion read it — so a blocker could clear and the thing it blocked
  would sit there with the graph holding the answer and nobody asking.

- **A fourth relation-kind property, `blocking`.** The source *waits for* the target, which is
  what `unblocked` reads. Split from `dependency`, which is *structural* — whether the source
  sits above the target in the type hierarchy — and is what `layering` reads.

### Changed

- **Several queries take turns rather than pooling their scores.** With more than one query,
  each query's ranking fills every Nth slot instead of all of them competing on summed RRF. It
  keeps everything pooling had on a correct extra phrasing (recall@5 1.00) and bounds what a
  wrong one costs (0.25 → 0.75). Weighting the task was tried first and removes the gain along
  with the risk. One query is unaffected.

- **`--mermaid` requires a UMD bundle, and says where to get one.** docir loads the runtime as a
  classic script — deliberately, since a `type="module"` script is fetched under CORS and would
  break the `file://` guarantee the published site is built around. mermaid 11 ships only ES
  modules, so the file docir's own docs named has not existed for a major version. The error now
  names `mermaid@10.9.3` and its URL rather than sending you to a package that does not contain
  it.

- **`Embedder.dimension` is gone.** Declared on the port and read by nothing: storage is
  width-agnostic and the one place two widths could disagree is checked inside `Embedding`.

### Fixed

- **`unblocked` announced a decision refining a *superseded* one as "ready to start".** It read
  `dependency`, which is structural; `refines` is a dependency and not a blocker, so a narrowing
  whose broader rule had just been retired was reported as good news. Latent across 34 edges in
  docir's own corpus.

- **`--also` and `--explain` reached the CLI and no MCP tool.** An agent could not ask for
  either. The tool-name test pinned names against the dispatcher and said nothing about
  arguments; it now checks that every CLI flag reaches the tool that mirrors it.

- **A document id in shipped prose must now resolve.** Two ADR ids were cited in docstrings
  before the decisions were recorded, and never resolved at all. Every id in the wheel's prose
  is checked against the store, with examples declared.

### Measured and rejected

Kept because the measurement is the useful artifact, not the code.

- **Pseudo-relevance feedback** — rewriting a query from its own top hits — cost 0.13 recall@5
  on docir's corpus. The first pass is already right 88% of the time, so feedback mostly
  amplifies the 12% where it was not. (adr-46b69a581c65)
- **A generative model, at all.** Not as a dependency and not as an extra. docir's caller is
  already a frontier model that has read the code; a 0.5–1.5B rewriter underneath it would be
  guessing at context the caller had and did not send. `--also` is what replaces it.
  (adr-27c63ad02695)

## [0.17.0] - 2026-08-17

Staleness measured a calendar and `orphan` measured `related:` frontmatter, so docir called a
document suspect because a cadence elapsed and called it unconnected because its author had
linked it the way most people do — by writing its id in a sentence. Both now read the corpus
that is actually there.

### Upgrade notes

- **Run `docir self upgrade`.** Two migrations land (0007 adds `document_code.digest`, 0008
  adds the `mentions` table) and the mention graph exists only after a reindex — until then
  `orphan` keeps firing on documents that prose already links.
- **Every peer in `.docir/stores.yaml` needs its own `docir reindex`.** A peer is opened
  read-only and never migrated (adr-fb938175f72a), so this build skips one whose index
  predates it, naming the store and the command that fixes it. That is the deliberate cost of
  the federation fix below; reads still answer from the remaining stores rather than failing.
- **Nothing is rewritten.** No document changes, no flag retired. The new digests are written
  only when you run `docir update <id> --verified`.

### Added

- **`docir check` reports `code-changed`: the code under a verified document moved.**
  `docir update <id> --verified` now fingerprints what each `code:` glob matched (contents and
  paths, sha256 truncated), and `check` recomputes and compares. This is the evidence half of
  staleness — the calendar answers "how long since somebody read this", this answers "has the
  thing it describes changed since". It needs no parser and no history: hashing contents rather
  than mtimes or a commit id means a clone, a checkout and a rebase are all silent. The digests
  live in **frontmatter**, not the index, because the index is gitignored and the finding is
  for whoever clones the repo. A warning, and not promotable: editing code before its docs is
  the ordinary shape of a change. `check --fix` leaves it — clearing it is a judgement, and a
  repair has nothing to read with. (adr-bd7c4f3c5764 named this as future work.)
- **A second relation graph, derived from prose.** Ids named in a body are scanned into a
  `mentions` table, rebuilt by `reindex` and never written back to frontmatter — `related:`
  stays the authored, typed layer. On this repo's own corpus that surfaced 451 edges nobody had
  hand-written. **`orphan` is the only check that reads it**, deliberately: `cycle` would report
  mutual citation, `dangling` is an error that gates a merge and a body naming a
  not-yet-written id is ordinary, `layering` needs a direction a mention does not assert, and
  the delete guard would refuse to remove a document because a paragraph quotes its id.
  `docir get` shows both directions (`mentions`, `mentioned_by`).
- **`docir context` expansion follows mentions**, after authored edges and in both directions.
  Measured before it shipped, which needed a new instrument — `benchmarks/run.py` allocates ids
  at load time, so its bodies cannot name one and its mention graph is empty. On
  `benchmarks/mentions.py`: recall@5 **0.84 → 0.93**, precision 0.33 → 0.37, MRR unchanged at
  0.86. That last figure is a property of the budget rather than of expansion — `seed_budget =
  limit - expand`, and the same sweep puts MRR at 0.83 for `expand=3`. `expand=1` and `expand=2`
  were indistinguishable on that fixture, so the shipped default is undistinguished, not
  measured-optimal.
- **`docir lint --deep` gains `unresolved-mention`** — an id named in prose that no document
  carries, one finding per document. Tier 2 and not promotable, measured first: all 47 in this
  corpus are documentation *examples* (`adr-0007` and friends, in the documents explaining the
  id format), so a Tier 1 warning would fire 47 times on a healthy corpus and never once on a
  defect. Filtering code spans does not rescue it either — 20 of the 47 sit outside code, while
  56 *resolved* mentions live only inside code spans.
- **`benchmarks/mentions.py`** — a corpus whose bodies carry `{key}` placeholders substituted
  after id allocation. It mints sequential ids, because random ones move ranking ties (the same
  code scored 0.79 and 0.81 on consecutive runs), and derives its task grouping from the corpus
  rather than a hand-written label — the first version's labels were wrong in the direction
  that flattered the feature.

### Fixed

- **A federated read against a peer indexed by an older docir crashed the whole command.**
  Every table or column a migration adds is one some peer will not have, and two were already
  live: `mentions` (0008) took down `context` and `get` with `no such table`, and
  `document_code.digest` (0007) took down every hydrate, which is `query` too. Through the
  daemon the user saw only "daemon closed the connection without responding". `peer_status` now
  compares the peer's `alembic_version` against this build's head, so **one rule covers every
  past and future migration** — a guard per column worked and had to be remembered, which is
  the failure mode itself. An *unknown* revision is from a newer docir and is allowed; a
  missing one is skipped, since "cannot say" is not permission.
- **`docir agent update` called a stamp-only rewrite an update.** Upgrading 0.14.0 → 0.16.0
  reported both skill files as `updated  v0.14.0 → v0.16.0` although neither template had
  changed in either release. A byte comparison cannot see that: the version stamp is written
  into the file being compared, so it differs on every upgrade by construction. The comparison
  now blanks the stamp, the action reports `unchanged`, and the misleading arrow is gone.
  The file is still rewritten — the stamp is the module's only persisted state, so skipping the
  write would repeat the same transition forever. (adr-9d2b4865689a)

## [0.16.0] - 2026-08-17

`docir self upgrade` cost a minute on a 300-document store and spent 96% of it recomputing
vectors identical to the ones already in the index. It now rebuilds in full only when the
index was built by a different version — which is the only time a full rebuild has anything
to do.

### Upgrade notes

- **Run `docir self upgrade`.** This release stamps nothing new and rewrites no markdown; the
  rebuild happens because the version moved, and it is the last slow one. Every upgrade after
  this that finds nothing to upgrade takes about a second.
- **Nothing else is required.** No migration, no flag retired, no document rewritten.
  `reindex` output gains a key and the human line gains a number.

### Changed

- **`docir self upgrade` resyncs instead of always rebuilding.** It reads the version stamp
  the index carries and takes the full path only when some other build wrote it. Measured on a
  315-document store: **65 s → 1.5 s** when the running build already indexed it, and 62 s
  when it did not — the expensive path is kept, because a release that changes how documents
  are read (chunk boundaries, the embedder) needs exactly that pass. The decision is the stamp
  rather than "did this invocation install a package", which is blind to a docir upgraded out
  of band. A skipped rebuild now says so, since a bare `0 documents` reads like a failure.
  (issue-cfeb6eaa31cc)
- **`docir check --fix` stopped paying the same price.** Its repair reindexed in full before
  allocating ids, and again after re-issuing duplicates; both are now changed-only, which is
  all that "make the index agree with the files" ever needed. 59.8 s → ~1 s on the same store.
- **A reindex reports vectors *and* documents.** 0.15.0 added the count and printed it as
  `N vectors`, but the number counts documents — the queue is keyed by document while each one
  writes a vector of its own plus one per `##` section, so a rebuild that wrote 1,326 vectors
  reported "315 vectors". `ReindexResult.vectors_written` carries the real figure and the line
  now reads `315 re-embedded (1326 vectors)`. `embeddings_recomputed` keeps meaning documents,
  and `docir embed --flush` keeps `embedded` as documents with `vectors` beside it, so nothing
  reading either key silently starts getting a 4x larger number.

### Added

- **`benchmarks/maintenance.py`** — the write path had no instrument, which is how a
  minute-long command went unreported while `benchmarks/latency.py` measured reads. It times
  reindex (full and changed), both upgrade paths, check, `check --fix`, `embed --flush` and
  build, and measures the embedding share by re-running the same rebuild against the
  model-free embedder rather than asserting it. Batching and thread-tuning the model were
  measured and rejected: the shipped default is the fastest configuration on the hardware
  tested.

## [0.15.0] - 2026-08-16

A one-change release: the flag that claimed to recompute your vectors is gone, because the
rebuild it skipped had been doing that all along and never said so.

### Upgrade notes

- **If you call `docir reindex --embeddings`, drop the flag.** It is now an unknown option and
  exits non-zero. Plain `docir reindex` does everything it did and writes the two stamps it
  skipped; `docir self upgrade` runs that for you.
- **Nothing else changes.** No migration, no index rebuild required by this release, no document
  is rewritten. `reindex` output gains a key.

### Removed

- **`docir reindex --embeddings` (breaking).** It selected a different operation rather than
  widening the one it named: it recomputed every vector and returned *before* the rebuild,
  writing neither the schema baseline nor the build stamp. So it did strictly less than the plain
  command for the same money — measured at 59 s against a full rebuild's 55 s over 152
  documents, because embedding dominates and both embed everything — and left `docir check`
  reporting `stale-index-build` against a store that had just been reindexed, which reads as the
  command having failed. 0.14.0's upgrade note told people to run it.
  A rebuild re-embeds every document it re-saves, so nothing was left for a second mode to do,
  and the case the flag was reached for is already covered: a vector records the model that
  produced it and a foreign `model_id` reads as dirty, so `docir embed --flush` recomputes
  everything after an embedder switch. The `embeddings` payload key and the MCP parameter are
  gone with it; a leftover key is ignored rather than reviving the path. **Use `docir reindex`,
  or `docir self upgrade`, which runs it.** (adr-6a4718fa7a7d)

### Changed

- **A reindex reports the vectors it recomputed.** `ReindexResult.embeddings_recomputed`, and
  `, N vectors` in the human output. A rebuild always re-embedded everything it re-saved and
  never said so, which is what made a separate flag look necessary in the first place.

## [0.14.0] - 2026-08-16

The release that lets a corpus rename its own vocabulary, and that tells you what a schema edit
costs before it is history. Two defects in section addressing are fixed underneath, so a document
that quotes markdown is finally read the way it is written.

### Upgrade notes

- **Run `docir self upgrade`.** That is the whole upgrade: a full `docir reindex` re-embeds every
  document, which is what this release needs, because chunk boundaries move for any document that
  quotes a fenced heading or has a short section sitting before a long one. It is index-only — no
  markdown is rewritten and no document's `updated` advances. (An earlier printing of this note
  also asked for `docir reindex --embeddings`; that is redundant after a full reindex, and it does
  not record the version stamp `check` reads.)
- **Nothing else is required.** `update --type`, `disable_types:` and the widened
  `schema validate` are all opt-in; a store that uses none of them behaves exactly as it did in
  0.13.1. `schema validate`'s exit code has not moved — it still reports a valid file as valid.
- **`docir schema validate` now prints a `conformance` block.** A script parsing its JSON gains a
  key; nothing it already read has changed shape.

### Added

- **`docir update <id> --type <name>` retypes a document.** Renaming a corpus's vocabulary was
  impossible through the CLI: `update` patched every frontmatter field except the one that selects
  the grammar the others are checked against, so a rename meant hand-editing the markdown the
  write path exists to own. The id is never re-minted, prefix included — it is the corpus's only
  address and is spelled out in every `related` edge pointing at the document, so a prefix records
  which type *minted* an id, never which type owns it now. Status is checked for membership in the
  target type and a status it does not declare is refused naming the flag that fixes it, never
  reset to `default_status` (which across a corpus rewrites every `accepted` to `draft` and reports
  success). The existing edges are re-validated against the new type even when the call does not
  supply them, the file moves into the new type's directory keeping its filename, and the vacated
  directory is pruned. A retype is not a content change: nothing is queued for re-embedding.
- **`disable_types:` subtracts a type from the resolved schema.** Merging only ever added — the
  core is merged whenever a `profiles:` key is present, `profiles: []` included — so `decision`
  and its `adr` prefix existed in every store forever, the name stayed addable beside a corpus's
  own, and the prefix could not be reused. It is applied after core + profiles + inline resolve,
  and it is refused when it names a type the schema does not define, one the same file also
  declares inline, or all of them. It deliberately does not consult the corpus: stranding
  documents on a disabled type is supported and reported as `unknown-type` beside the
  `schema-drift` finding naming the cause.
- **`docir lint --deep` reports `ambiguous-heading` and `unqualified-section-ref`.** The first is
  a heading used twice in one document: section reads resolve to the first match, so the rest is
  reachable only by fetching the whole body, and nothing said so. The second is prose naming a
  section that lives in a *different* document — what a document split leaves behind. It only
  speaks about headings unique to one document, because a check that cannot say which document
  holds the section should not claim one.
- **`docir lint --deep` reports `oversized-section`.** A section past the chunk ceiling is split
  and only the first piece keeps the heading, so the rest is text `context` can retrieve but
  `matched_section` can never name and `get --section` will not return on its own. The check runs
  the splitter and reports what it produced — which section, and how many pieces are unaddressable
  — so it has no threshold of its own to tune. Advisory, like every Tier 2 finding: a long
  reference table is frequently right as it is.
- **`docir agent install --agent claude-writing` — a second, opt-in skill covering how to write
  the documents**, beside the one covering how to drive the CLI. Four rules: name each concept
  the same way everywhere, give one document one purpose (its `type` says which), state each fact
  once and link to it with a typed edge, and keep each `##` section under ~1,200 characters — the
  size docir embeds at, so a longer one is split mid-paragraph and retrieves worse. It carries no
  word limit: length follows purpose, and `docir lint --deep` already warns on size. Not installed
  by default; `AGENTS.md` lists it once it exists.

### Changed

- **`docir schema validate` measures the corpus, not just the file.** It answered one question —
  does this file load? — about the file alone, so the command a person runs immediately after
  editing `docs-schema.yaml` reported `valid: true` at the exact moment a corpus could have left
  the type system. Disabling a type strands every document of it; adding a `required:` field
  strands every document written before it. It now also reports how many documents carry a type,
  status, required field or relation kind the schema no longer accepts, by kind, with a bounded
  sample of ids. No rule is added: it runs the same four schema findings `docir check` does, from
  one shared implementation. It reads the *files*, not the index — a schema edit is a hand edit,
  which is when the index is behind — and it still opens no database, so a store too broken to
  start stays diagnosable. The **exit code does not move**: gating here would fail during a
  correct migration, which necessarily passes through the stranded state.
- **A daemon-answered command no longer imports SQLAlchemy.** Such a command is a socket client
  and never builds a container, so it was paying ~360 ms for SQLAlchemy and Alembic it does not
  use. `python -m docir version` now loads 655 modules instead of 925. Warm-daemon p50 over 25
  documents: `context` 0.86 → 0.53 s, `search` 0.87 → 0.55 s, `get` 0.83 → 0.53 s. `--no-daemon`
  is unchanged, which is the control — that mode does build a container and correctly still pays.
- **`AGENTS.md` now points at the Claude skill instead of inlining it.** The block used to
  hold the whole ~500-line guide, so a repo installing both targets committed the same text
  twice and only one copy was refreshed — the duplication docir exists to prevent, in docir's
  own output. It now carries the skill's frontmatter `description` verbatim plus a link to
  `.claude/skills/docir/SKILL.md`, and shrinks to ~8 lines. Existing blocks migrate on the
  next `docir agent update`, which reports the replacement; surrounding house rules are
  preserved as before.
- **`docir agent install --agent agents` also writes the skill it links.** Previously it wrote
  a block and no skill file at all. `docir agent update` expands the same way, so a block whose
  skill was deleted is repaired rather than left naming a file that is not there.

### Fixed

- **A `##` inside a fenced code block is no longer read as a section heading.** The chunker
  already skipped fences; the section read/edit path did not, so a document quoting a markdown
  template disagreed with itself. `docir get <id> --section` returned a fragment ending in an
  *unclosed* fence, an unknown-heading error listed phantom headings as real, and
  `docir update <id> --replace-section` ended the span at the phantom boundary — writing the
  replacement and stranding the rest of the quote at top level, reporting success. All three
  paths now read one shared fence-aware scanner.
- **A short section before a long one no longer erases the long one's heading from the index.**
  Merging a below-minimum section forward and then hard-splitting the result kept only the first
  piece's heading, so the following section named no chunk at all — `docir get <id> --section`
  still returned it, but `matched_section` could never point there. A merge that would overflow
  the chunk ceiling is now declined: it saves no vector and costs an address.
- **`docir schema validate` counts distinct documents.** `affected` summed the per-kind counts,
  so a schema edit that stranded one document on both its status and a new required field printed
  "14 of 8 document(s)".

### Documentation

- **The project has a CONTRIBUTING guide, a security policy and issue/PR templates.** `.github/`
  held only workflows, so the gate suite, the module rules and the benchmark harnesses were
  discoverable only by reading `CLAUDE.md` — written for an agent already working in the repo
  rather than for someone arriving at it. The templates are project-specific: the bug form asks
  for `docir self status` and whether the failure survives `--no-daemon`, because a daemon holding
  old code answers from it and a stale answer imitates a correct one. `SECURITY.md` documents the
  surface docir actually has — the daemon socket, whose only boundary is filesystem permissions;
  the two narrow network calls; and that `docir build` passes raw HTML in a body through to the
  page, which is safe for a reviewed corpus and worth knowing for anyone publishing contributed
  documents.
- **The README hoists the quickstart and the deep rationale moves into the store.** The
  architecture note is split into the shape plus five documents — the write path, the read path,
  the file format, the validation tiers and maintenance — and every long section is broken into
  individually retrievable ones. docir's own corpus is now written to the rules the new writing
  skill teaches.
- **docir's own prose is machine-checked against the CLI.** Every `docir ...` invocation in the
  README, `CLAUDE.md`, the packaged skill, the six `CONTRACT.md` files, every file in the store
  and every docstring under `src/` must resolve to a real command with real flags. 37 stale
  invocations survived in docstrings after the markdown side was already clean.
- **New benchmark harnesses.** `benchmarks/latency.py` measures read latency by corpus size and
  daemon mode, `benchmarks/chunking.py` measures the splitting rules against a corpus that
  declares its real headings by hand, and `benchmarks/tokens.py` prices `context` against a grep
  baseline. `benchmarks/run.py` is the wrong instrument for a chunking change — its corpus has no
  section over the ceiling and none quoting a fenced heading, so a broken splitter scores what a
  working one does.

## [0.13.1] - 2026-08-13

A patch for one real defect in 0.13.0's diagram support, plus the package metadata that
should have shipped years of releases ago.

### Fixed

- **A document that *writes about* diagrams no longer publishes a diagram runtime.** The
  checks deciding "does this page draw something" were substring tests over the rendered HTML,
  so the filename `mermaid.min.js` and the marker class appearing in ordinary prose satisfied
  them — this repository has two such documents. A corpus that draws nothing would have had
  ~3 MB of JavaScript written beside its pages, and a page that only documents the flag would
  have loaded it. Both checks now test the raw `<div class=...>` and `<script src=...>` tags,
  which prose cannot forge: it reaches the page escaped.

### Documentation

- **The package is findable.** `keywords` and `[project.urls]` ship with the distribution, so
  the PyPI page links to the source, the published corpus, the changelog and the issue
  tracker. It previously linked nowhere at all.
- **The README quoted superseded benchmark figures.** It carried `recall@5 0.96/0.93` and
  `MRR 0.95/0.80` from before the 2026-08-03 corpus re-base, which `benchmarks/README.md`
  explicitly warns not to compare across, plus a sentence that had conflated `search`'s MRR
  with its recall. The current corpus reads **0.97 (MRR 0.97)** against **0.80 (MRR 0.76)**,
  and the corrected paragraph leads with the split an average was hiding: the two embedders
  are within noise on questions worded like the documents, and **0.95 against 0.65** on
  questions that share no vocabulary with them. Both harnesses were re-run to confirm.
- **The architecture note draws its own diagram** — the first mermaid fence in docir's own
  store, and the worked example for 0.13.0's diagram support. The Pages workflow fetches a
  digest-pinned runtime and asserts it reached the site.

## [0.13.0] - 2026-08-13

The release that lets a store read the repository next door, and lets an author draw. Both are
opt-in and neither changes what a store already does.

### Upgrade notes

- **Nothing is required.** A store with no `.docir/stores.yaml` and no `mermaid` fences behaves
  exactly as it did in 0.12.0, byte for byte — a single-store read still carries no `store` field.
- **Federation is a file you write.** `.docir/stores.yaml` lists peer store homes; commit it, so
  the set is the team's rather than each machine's. Peers open read-only and an unreadable one is
  skipped with a warning, so a colleague's unbuilt index is never your outage.
- **`docir build` publishes one store**, and did so incorrectly for the few hours federation
  existed before this release. If you built a site from a store with peers during that window,
  rebuild it — pages for another repository's documents may be sitting in your output directory.
- **`--mermaid` needs a bundle you supply.** docir does not ship mermaid's browser build; without
  the flag a `mermaid` fence publishes its source, exactly as it did before.

### Added

- **Reads federate across declared stores; writes never do.** In a multi-repo organisation the
  decision governing the service you are editing lives in the platform repo, and an agent that
  cannot see it re-decides. A store now declares peers in a committed `.docir/stores.yaml`
  (relative paths resolve against the store, so a clone works unchanged), and `context`,
  `query`, `search` and `get` answer from all of them. `--store <path>` adds one for a single
  invocation, resolved against the working directory the way every other path argument is.

  **Peers are opened read-only at the database** — `mode=ro`, so SQLite refuses a write rather
  than docir promising not to attempt one. Peers get their own construction path because
  `build_container` runs migrations and creates directories, and a peer is someone else's
  repository. A peer that cannot be read is **skipped with a warning, never fatal**: its index
  is derived and gitignored, so a colleague's fresh clone would otherwise be everyone's outage.

  **The merge sorts on `similarity`, never `score`.** `score` is reciprocal-rank fusion — where
  a document placed *within its own store* — so comparing two stores' scores compares the sizes
  of their corpora. Hits with no vector are appended round-robin per store rather than treated
  as 0.0, because absent still means *not scored*. Every row carries `store` while federating;
  a single-store read is byte-identical to what it returned before.

  `docir_context`, `docir_search`, `docir_query` and `docir_get` take the same list as a
  `stores` argument, so an MCP-only agent is not restricted to the committed set — the two
  transports would otherwise answer different questions, which is what the MCP module exists to
  prevent. A test asserts the parameter against `FEDERATED_COMMANDS`.

  The merge choice is now measured, not asserted (`benchmarks/federation.py`): on the same
  corpus split in two, merging on `similarity` scores recall@5 **0.91 / MRR 0.93** against
  rank-merge's **0.88 / 0.72**, with a single store's 0.97 / 0.97 as the ceiling. Cross-store
  RRF over the lists the stores return *is* rank-merge — every document appears in exactly one
  list, so its fused score has one term. About six points of the recall a split costs are the
  graph rather than the ranking: 8 of the corpus's 17 edges cross the split, and an edge cannot
  cross stores.

  **`docir build` stays single-store**, explicitly. It is assembled from `query` plus one
  `get` per document — both federated — so a store declaring peers published their documents
  into this repository's site while the summary line still named this store. A published page
  is a copy, and a copy of a peer's decision goes stale the moment that repo edits it, which
  nothing in the site could detect; the peer publishes its own site anyway.

  Supersedes the federation exclusion in adr-20eec6e2e2ca. See adr-fb938175f72a.

- **`docir build` draws `mermaid` fences as diagrams.** A fenced `mermaid` block is the one
  code block whose author meant the picture rather than the text; published as a highlighted
  code block, a sequence diagram in an architecture note is a wall of arrows the reader has to
  compile in their head. It now renders as a figure wearing the code block's frame, with the
  diagram inside it.

  **The runtime is a build input, not a bundled asset** — the same call `--logo` makes.
  Mermaid's browser bundle is megabytes of JavaScript, and vendoring it would put it in every
  wheel, every CI image and every install's supply chain to serve the corpora that draw
  diagrams. `docir build --out site/ --mermaid path/to/mermaid.min.js` supplies it; docir
  writes it beside the pages and loads it from there with a relative classic `<script>` — never
  a CDN and never a module, both of which break a site opened from `file://`. It is written
  only when some document actually drew a diagram, and loaded only on the pages that have one.

  **Without the flag the diagram publishes its own source**, framed and copyable, exactly as
  the code block did — a page whose runtime is absent is no worse than it was. Diagrams redraw
  on a theme change, because mermaid bakes its palette into the SVG at render time, so a
  diagram drawn in light mode would otherwise stay dark-on-dark after the toggle.

## [0.12.0] - 2026-08-09

The release that made upgrading docir a docir command. An upgrade used to be three steps a
user had to know about and run in order, documented in one release's notes — and two of the
things that needed doing were invisible from inside the store. `docir self upgrade` is all of
it: install the new docir, re-execute as it, rebuild the index, refresh the agent instructions,
report what is left.

### Upgrade notes

- **Migration `0006` runs on first use** (`index_build`, one row). Additive, no backfill: the
  store does not know which docir built its index until the next rebuild, and until then
  `stale-index-build` reports nothing. Absent means *unknown*, not stale.
- **Run `docir self upgrade` once per store after upgrading.** It is `reindex` + `agent update`
  + `check`, in the order they have to run, and from this release on it also installs the new
  docir where docir owns its environment.
- **`docir check` may report `stale-index-build`** on a store that was clean yesterday: the
  index was built by a docir that is no longer installed. A warning, never a `--strict`
  failure — every store is in that state between an upgrade and its next rebuild.
- **`DOCIR_UPDATE_CHECK=1`** is new and off by default: the daemon then checks PyPI once a day
  and every command names a newer release on stderr. Nothing reaches the network without it.

### Added

- **`docir self upgrade` installs the new docir too, then re-executes as it.** The package
  step runs first and hands off with `os.execv`, because the process running the installer is
  the code being replaced: everything after that call would otherwise be the old build's work,
  starting with the stamp recording which version built the index. A hidden `--upgraded-from`
  carries the outgoing version into the new process, so the report still names it, and doubles
  as the loop guard.

  **An installer runs only where docir owns its environment** — a `uv tool` install, a pipx
  install, a virtualenv. A checkout or path install belongs to a project whose lockfile decides
  its version; an ephemeral `uvx` environment has nothing to upgrade; an unrecognised layout
  gets no guess at all, because running the wrong installer against the wrong environment is
  worse than doing nothing. Each of those says why and resyncs the store anyway. `--no-package`
  skips the install (adr-a555ee6bc484).

- **`docir self status` — what is installed, how, and whether anything newer exists.** A file
  read: it reports the last cached answer, and an absent `latest` means *nobody has checked*,
  never "up to date". `--refresh` asks PyPI — docir's only network call — and skips even that
  when the answer is already from today.

  **`DOCIR_UPDATE_CHECK=1`** makes it ambient: the daemon refreshes the answer in the
  background and every command names a newer release on stderr. Off by default, on the argument
  `DOCIR_SCHEMA_NOTICE` already makes about a notice that repeats until someone acts on it —
  and because a documentation tool that phones home unasked is not one people keep installed.

- **`docir self upgrade` — the steps that follow a new docir release, as one command.** It
  reindexes, refreshes any installed agent instruction file to the running version, then
  reports what `check` still finds, in that order: the rebuild first because the index is
  derived and gitignored and is the only place the schema baseline and the build version are
  recorded, `check` last so its findings describe the state you are left in.

  It does **not** install docir. This process is the code that would be replaced, so
  everything after that call would still be the old build's work — starting with the rebuild
  that stamps which version built the index, which would then record the version on its way
  out. Upgrade the package the way you installed it (`uv tool upgrade docir`), then run this.
  A `self` group rather than a top-level verb, because `docir update <id>` already means
  "edit a document" (adr-31aa7aa60d11).

- **`docir check` reports `stale-index-build`**: the index was built by a docir that is no
  longer installed. The schema baseline cannot see this — it compares *schemas*, so it is
  silent for a release that changes how documents are read rather than what they must
  contain, and chunked embeddings rewrote every vector in the index without touching a type,
  a status or a cadence. Migration `0006` adds the one-row `index_build` table; `reindex` is
  its only writer, as it is the baseline's.

  A warning, on inequality rather than "older than": a downgrade needs the same rebuild, and
  every store is in this state between an upgrade and the next rebuild, so an error kind
  would red-light every repository on release day. A store not rebuilt since the table
  arrived reports nothing — absent means unknown, not stale.

### Documentation

- **An "Upgrading" section in the README, and `run-f4a756206fe0` in the store**: what to run
  after a new release, per store. The upgrade path existed only as one release's "Upgrade
  notes" — a section nobody reads twice — while the things that need doing are the same every
  time and two of them are invisible. `reindex` is the only writer of the schema baseline, so
  a store that has not been reindexed reports no `schema-drift` at all; and nothing detects a
  stale `<!-- docir:vX -->` stamp, so an agent can keep reading a guide for a version that is
  no longer installed. 0.11.0 shipped with docir's own skill file claiming v0.10.0, which is
  the case in point.

- **`docir agent update` is now step 3 of the release runbook** (`run-30aceb4eacc6`), between
  the version bump and the commit — the stamp is rendered from the running `__version__`, so
  any other order stamps the previous release.

## [0.11.0] - 2026-08-07

The release that made a schema change visible. docir's types and cadences ship in the package as
much as in your `docs-schema.yaml`, so an upgrade could quietly change what a store enforces —
and every consequence was reported while the cause was not. Now `check` names the change, and
names the documents it breaks.

### Upgrade notes

- **Migration `0005` runs on first use** (`schema_baseline`, one row). Additive, with no
  backfill: your store has no baseline until its next `docir reindex`, and until then
  `schema-drift` reports nothing. Absent means *unknown*, not unchanged — an upgrade must not
  report your whole schema as newly added.
- **Run `docir reindex` once after upgrading.** It records the baseline, so the next schema
  change is the one you get told about.
- **`docir check` may report findings on a corpus that was clean yesterday**, all of them
  warnings: `missing-required` for a document lacking a field its type requires, and
  `unknown-relation-kind` for an edge whose kind your schema does not register. Neither fails
  `--strict`. They describe rules your documents no longer satisfy — nothing about the documents
  changed.
- **`DOCIR_SCHEMA_NOTICE=1`** is new and off by default: it prints schema drift on stderr after
  every command, for the change nobody will run `check` to discover.

### Added

- **`docir check` reports that the schema itself changed, as `schema-drift`.** A store's types,
  statuses and cadences come from the installed docir as much as from `docs-schema.yaml` — the
  core and the profiles are compiled into the package and re-merged on every command — so an
  upgrade could change what an untouched store enforces with no local edit and nothing in
  `git diff` to review. Every consequence was reported (`unknown-type`, `unknown-status`, the new
  `missing-required`) and the cause was not, so the findings appeared to come from nowhere
  (issue-d891ab5501e6).

  The index now records the resolved schema it was last rebuilt against (migration `0005`,
  one row, derived like every other table), and `check` reports the difference one line per
  change: `+type test_plan`, `type decision: required [] -> ['owner']`, `prefix 'issue' -> 'bug'`.
  **`reindex` is the only writer of that baseline** — it is already the "make derived state agree
  with the sources" command, and giving drift its own acknowledgement verb would add a ritual
  whose only effect is to silence a report. Until you run it, `check` keeps naming the change.

  A warning, so `--strict` stays green: the corpus is untouched and it is the *rule* that moved.
  A store with no baseline reports nothing — absent means unknown, not unchanged, so an upgrade
  does not report the whole schema as new. `DOCIR_SCHEMA_NOTICE=1` additionally prints the drift
  on stderr after **every** command, for the change nobody will run `check` to discover; it is
  off by default because a notice that repeats on every command until someone reindexes is how a
  warning stops being read. Also exposed as the `docir_schema_drift` MCP tool.

- **`docir check` reports a new warning kind, `unknown-relation-kind`**: an edge whose kind the
  relation registry no longer lists. It completes the hand-edit family — a tag the registry does
  not know and a status the type does not declare were both reported, while an unregistered
  *kind* was served by `get`, traversed by `context`, and flagged by nothing; only rewriting the
  edge was refused, by Tier 0 (issue-0e3d1d9c81d3).

  A warning, and on stronger grounds than its siblings: the edge keeps working.
  `Schema.relation_kind` falls back to the core properties, so a kind the registry has stopped
  listing is still cycle-checked and still read as a dependency by the layering check. What is
  lost is the report, not the behaviour. A registry that registers *nothing* stays permissive —
  that is every schema predating typed edges, and reporting there would fire on all of them.
  `check --fix` does not touch it: rewriting `depends_on` to `relates_to` would silently drop a
  dependency claim, which is a guess about meaning rather than a mechanical repair.

- **`docir check` reports a new warning kind, `missing-required`**: a document that does not
  carry a field its type declares as `required`. Every other classification finding needs a
  hand-edit or a merge to occur; this one does not. Core and profile types are compiled into the
  package and re-merged on every command, so a release that adds a `required:` entry changes what
  an untouched store enforces — no local edit, nothing in `git diff` to review. Until now the
  corpus was silently non-conforming and the first report was a *write* being refused:
  `docir update <id> --set-title` failing on a field the caller never mentioned, one document at
  a time (issue-8f6576cd7bc9).

  It is a **warning**, and `--strict` stays green — for the reason `unknown-type` is one,
  sharpened: the rule change ships in the package, so an error kind would red-build every repo on
  the release that added the field, which is exactly how the `--strict` gate became unusable the
  first time. `--strict-all` still covers anyone who wants it fatal.

  Type-declared fields only — a core required field is what makes a document parse at all, so an
  absent one is already `malformed`. One finding per document naming every field it lacks, rather
  than one per field, so a schema requiring three of them does not triple the output on a corpus
  that predates them. `check --fix` deliberately does not touch it: an owner or a tag is a
  decision, and there is no value to fill in. The emptiness rule is now *shared* with Tier 0
  (`validation.is_absent`) rather than restated, so `check` cannot call a document conforming
  that the next write refuses.

## [0.10.0] - 2026-08-06

The release that made docir answer for the code. A document can name the code it governs, a
ranked hit names the section that matched, and the corpus reaches humans as a site and agents as
MCP tools — with the daemon keeping the index in step with hand edits along the way.

### Upgrade notes

- **Migrations `0003` and `0004` run on first use** (per-section vectors, `document_code`). Both
  are additive; `0003` marks every embedding dirty, so the first read after upgrading has no
  semantic signal until the next write or `docir embed --flush`. Chunk vectors are ~7× more rows
  than document vectors, and `context` loads every active vector per call, so the practical
  corpus ceiling drops by about that factor.
- **A `docs-schema.yaml` whose `required:` names something no document can carry now fails to
  load.** Such a schema already rejected every write of that type, so nothing that worked stops
  working — but the error moves from the write to the load, which is where it belongs. If you
  have one, the message names the fields that would have worked.
- **`required:` is now enforced for collections.** `required: [tags]` used to load and check
  nothing; it now means "at least one tag", so a document written without one is refused. Only
  affects schemas that already listed a collection field.
- **The daemon watches `docs/` and reindexes what changes** — on by default. `DOCIR_WATCH=0`
  opts out; `--no-daemon` runs never watch, so CI still runs `docir reindex` explicitly.
- **`fastmcp` and `watchfiles` are default dependencies**, not extras. An agent that only speaks
  MCP cannot install an extra it has not been told about.

### Changed

- **Enforcement of decisions against code closes as a decision, not a feature** (adr-b2cfed9d5888).
  It was the last strategic gap in the competitive survey and the one docir had never answered:
  archgate binds an ADR to an executable rule that fails CI. With `code:` shipped there was finally
  something to bind *to*, so the question was live — and the answer is that a decision which can be
  mechanically enforced is enforced by a **test**, in the project's own language and runner, with
  `--code tests/test_x.py` recording which decision that test enforces. `check`'s `unmatched-code`
  then covers the failure a rule file has too: the enforcement was deleted and nothing said so.

  The review-time half is a **notice, never a gate**: docir's own CI now prints the decisions a pull
  request's changed files declare they govern. Failing a build because you touched governed code
  punishes the ordinary case, and a check cleared by clicking is a ritual rather than a human
  reading a decision — the argument adr-bd7c4f3c5764 already made for staleness. What docir will not
  own: a rule DSL, a sandbox for user-supplied rules, and per-language static analysis.

### Fixed

- **A `required:` field name no document can carry is now refused when the schema loads.**
  `required:` was checked only for being a list, while Tier 0 reads the field off the document —
  so `required: [commit]` loaded happily and then rejected *every* write of that type, forever,
  with a message naming the write rather than the schema and no flag able to satisfy it
  (issue-e3c4dfad4f7b). The same class of defect as an undeclared status target, which this
  loader already caught; it is now reported the same way, naming the fields that would have
  worked. The allowed set is derived from the `Document` dataclass rather than written out, so it
  cannot fall behind a new field, minus `path` — the file store assigns that *after* validation
  runs, so requiring it would reject every create.

  Fixing that surfaced the other half: with real field names now expressible, `required: [tags]`
  was accepted and enforced nothing, because an empty tuple is neither `None` nor a blank string.
  Emptiness now covers collections, so `required: [tags]` means "at least one tag". `False` is
  still a value, not an absence — `archived: false` is the normal state of a document.

  The shipped schema's own comment described `required` as "extra frontmatter fields", which is
  what invited the unsatisfiable name; it now says it takes an existing document field and lists
  them.

### Added

- **A ranked hit says which section matched.** Every hit from `docir context` now carries
  `matched_section` — the heading of the section whose vector earned the document its rank —
  and it is exactly the string `docir get <id> --section "<heading>"` takes.

  Chunked embedding (adr-927aa43d9635) made a long document reachable by any of its sections and
  then reported only the document: the winning vector was known inside `semantic_ranking` and
  discarded one line later. An agent was left with the two moves the section read was built to
  remove — pull the whole body, or discover the headings in a second round trip, since an
  unknown heading errors *listing* the real ones (issue-afd25273ff1f).

  The collapse to one score per document now keeps the winning *candidate* rather than just its
  score: `VectorCandidate` and `SemanticHit` carry the heading through `HybridScorer` into
  `FusedScore` and out onto the skeleton. Absent means the match is not addressable as a
  section — the document's own vector won, the hit was lexical or graph-reached, or the winning
  chunk is a preamble or the continuation of an over-long section, neither of which has a name
  `--section` would accept. It is the "absent means unknown, never zero" rule `similarity`
  already follows.

  It is `matched_section`, not `section`: `DocumentView.section` already means "the body was
  narrowed to this one", a different claim on a sibling DTO, and one word meaning two things is
  how `stale` came to name three concepts (issue-d8295c5c76d1).

  Costs **12 tokens** per `context` result set on the benchmark corpus — measured by suppressing
  the field and re-running (484 vs 472), not by comparing against a figure from a smaller corpus —
  and saves a body fetch whenever a hit is a long document. Ranking is bit-identical with and
  without it: recall@5 0.97, MRR 0.97.

- **A document can name the code it governs.** `docir add --code "src/auth/**"` (and
  `docir update <id> --set-code ...`) records repo-relative globs in frontmatter, and they
  ride on every read view — `get`, and the skeletons `query`/`search`/`context` return — so
  "does this decision concern the files I am about to change" no longer requires reading
  bodies and guessing.

  docir validated the document graph against itself and nothing else: an ADR could say "SQLite
  is the derived index" with nothing tying it to `platform/persistence/`. That is the
  "why is this document worth writing" argument the tool did not make, and it also blocked the
  AST-anchored staleness signal adr-bd7c4f3c5764 defers — there was no anchor to hang it on
  (issue-90aea6d1b891).

  The schema *appeared* to offer a way in and did not: `required:` is documented as "extra
  frontmatter fields this type must carry", but it is checked with `getattr` on the entity, so
  a name that is not already a field rejects every write of that type forever, with no flag
  able to satisfy it (filed as issue-e3c4dfad4f7b). Hence a real field: on `Document`, in the
  markdown frontmatter, and in the index (`document_code`, migration `0004`, a child table
  like `document_tags` because the value is a set and the question asked of it reads the
  patterns).

  **Tier 0 checks the shape and nothing else.** An absolute path, a `..` segment, a backslash
  separator and an empty entry are refused — each is a pattern that can never match anything.
  A well-formed pattern matching nothing *today* is accepted, deliberately: a decision is
  routinely written before the code it decides, and code moves without the decision becoming
  false. Making that a write error would teach authors to omit the field, which is the state
  this exists to leave; it is a Tier 1 question, and the `check` finding for it is not built
  yet (step 2 of issue-90aea6d1b891).

  **`docir query --code <path>` asks the question in the other direction** — which documents
  declared they govern this file. Repeat the flag for several paths (any match counts), which
  makes `docir query --code $(git diff --name-only main)` the set of decisions a branch should
  be read against. Like `--stale`, it is a predicate SQL cannot express, so it is applied after
  the query and **before the limit**: `--code x --limit 1` means one governing document, not
  "the governing ones among the first document".

  Matching is **textual, not a filesystem walk**, and that is the load-bearing choice: the
  branch that *deletes* a file is exactly when the decisions governing it must be re-read, and
  resolving through the working tree would answer "nothing" for precisely that case. The
  grammar is `pathlib`'s (`**` crosses separators, `*`/`?` do not, `[...]` is a class), so a
  pattern means the same thing to `check` and to `query`. A document governing a directory
  governs what is in it — `src/auth` answers for `src/auth/login.py` — because a miss here
  costs a decision nobody read, and a false hit costs a glance.

  **`docir check` reports a glob that matches nothing** (`unmatched-code`, a warning). The
  write path accepts a pattern naming code that does not exist, so the "does it still match"
  question has to be asked later, by the command that reports shape and age — and asked as a
  warning, because the corpus is intact: a pattern is out of date, not broken. `check --fix`
  deliberately leaves it, like `malformed` and `unknown-type`: only a human knows whether the
  glob is stale or the document is.

  The check is **skipped entirely when the store has no repository above it**
  (`Settings.code_root`, the `.git` walk `is_unintended_global_fallback` already uses, started
  at the store). A global `~/.docir` has no tree to resolve a repo-relative pattern against, and
  reporting every pattern in it as missing is the "warning that fires on correct usage" failure
  the cycle and layering checks were each fixed for. A pattern absent from the resolved map is
  likewise *unresolved*, not missing — the rule `similarity` follows, where absent means "not
  scored" and never "scored zero".

  `content_hash` sorts the globs, for the reason it already sorts tags: the file keeps the
  author's order and the index returns them sorted, and without the sort a reindexed document
  read as hand-edited — which would make `--replace-body`, the one mode the divergence guard
  blocks, refuse a write that loses nothing. The published site grows a **Governs** panel
  listing the patterns as text, never as links: the store knows the globs but not the
  repository they resolve against, so a link would be a guess at a forge URL.

- **Relation kinds can declare what they mean.** `relation_types:` now also takes a mapping
  of kind to properties, beside the list form it has always accepted:

  ```yaml
  relation_types:
    governs:     {dependency: true}
    duplicates:  {symmetric: true}
    replaced_by: {successor: true}
    blocks:      {}                  # registered, all defaults
  ```

  `symmetric` means both directions are one statement, so a mutually-referencing pair is not
  a `cycle` finding. `dependency` means the source relies on the target — the only claim the
  Tier 1 `layering` check reads. `successor` means the *incoming* direction answers "is this
  still current?", so `docir context` follows it backwards.

  Those three questions were previously answered by three hardcoded name sets in three
  modules, and a kind registered by a custom schema could join none of them. It was a
  first-class Tier 0 citizen — validated, constrained by `allowed_relations`, round-tripped
  on disk — and silently exempt from every structural check that reads meaning. `replaced_by`
  could not be followed backwards at any price.

  Defaults are asymmetric on purpose: `symmetric` is false, so a custom kind is still
  cycle-checked and keeps the coverage it had before kinds were distinguished at all, while
  `dependency` and `successor` are false so it adds no warning and changes no traversal until
  asked. The core six carry their properties in code rather than in the core schema file — an
  inline-only schema never merges that file, and a non-symmetric `relates_to` there would
  reintroduce the bug below. The list form still parses and still means defaults; nothing to
  migrate. `docir schema show` reports the resolved properties of every kind.

- **The published site links a document id written in prose.** A body cites another document
  by its id, which is the only identifier a document has — and written plain it published as
  an unlinked string of hex, so the one canonical way to cite a document was also the one that
  gave the reader nothing to follow. Ids are linked from the markdown token stream rather than
  by rewriting the HTML, which is what keeps the pass out of fenced code, out of text that is
  already a link, and off a document's own id.


- **`docir build --out site/` — the store as a static site.** docir was CLI-only, which
  quietly assumed the people who must approve a decision are the people who run commands.
  They are not: a PR reviewer, a new hire and a manager all read decisions and none of them
  will type `docir get adr-3f9a2b1c7d4e`. Log4brains' whole pitch is publishing ADRs this way.

  One HTML page per document plus a filterable index, entirely self-contained — inline CSS,
  no external requests — so it opens from `file://` and publishes to GitHub Pages or S3
  unchanged. It renders what no other ADR site can: the **typed relation graph in both
  directions**. Outgoing edges come from frontmatter; incoming edges are inverted from every
  other document, because a reader landing on an old decision needs to know something
  replaced it — and that edge lives on the *other* document. A `supersedes` inbound edge
  becomes a banner above the body rather than a line in a list. Staleness, owner, tags and
  dates are on the page; a dangling edge stays visible as a bare id, so the site shows the
  same broken reference `docir check` reports.

  The site is derived like the index: `--out` is regenerated on every build, so a document
  deleted from the store cannot survive as an orphaned page. A directory that is not empty
  and was not built by docir is refused unless `--force` — `--out` is a path a person types,
  and a typo pointing at `src/` should not be answered by writing HTML into it. Inactive
  documents are published (following a decision to the one that replaced it is the point);
  archived ones need `--include-archived`.

  It is a new leaf module, `publishing`, that imports nothing from `documents`: it takes the
  documents as **data** — the same JSON `docir get` returns — so the site is a projection of
  the public contract rather than a second reader of the aggregate.

  Seven layout problems were found by opening the result in a browser rather than by reading
  the markup, and every one of them is now pinned by a test. The index was a four-column
  table that measured 426px at a 390px viewport — the page scrolled sideways — with rows
  388px tall, so 105 documents showed two per screen; it is a grid list that reflows, at
  191px a row. Every document printed its title twice, the second one larger, because docir's
  own convention restates it as the body's first line and a body `h1` outranks the page
  heading. Type, status and tags rendered as three identical grey pills, so one page read
  `architecture · active · architecture · persistence · retrieval` with the same word meaning
  two different things. The relation graph sat under the body — 4,068px down one ADR,
  ~13,000px down the architecture document — and moving it up buried the document under 21
  inbound links instead, so long lists are now `<details>` that show their count collapsed.
  Body headings had no ids at all, so there was no way to link a section and no contents
  list; there are now anchors on all of them and a table of contents above the body. The
  index also read "105 documents · 105 of 105" until you typed something, and every page
  logged a favicon 404.

- **`docir build` says so when the site would be empty.** `.docir/docs/` is committed and
  the index is gitignored, so a fresh clone has no index at all — and `build` reads the
  index, not the files. It wrote a site with an empty document list and exited 0, which is
  indistinguishable from a store that is genuinely empty. It now warns on stderr and names
  the fix (`docir reindex`). Still exit 0: an empty store is legitimate.

- **A Pages workflow publishing docir's own documents** — `.github/workflows/pages.yml`,
  which is also the copyable example. It reindexes from the committed files, gates on
  `check --strict` so a corpus with duplicate ids or dangling edges is never published,
  builds, and asserts the page count before deploying. Both paths were rehearsed against a
  pristine clone: with the reindex it publishes 105 documents, without it the gate fails.

- **The daemon watches `docs/` and reindexes what changes.** docir has always *permitted*
  hand-editing a body — it is in the README's "what you may edit by hand" table — and then
  asked you to remember `docir reindex`. Until you did, every read answered from a stale
  index: `get` returned the old body, full-text missed the new words, the vector was never
  recomputed, and nothing anywhere said so. Basic Memory, qmd and sqlite-memory all watch;
  docir did not.

  A debounced watcher now runs `reindex --changed` inside the daemon within about a second
  of an edit. Automating it is safe for the reason the whole architecture rests on: the files
  are canonical and the index is derived, so a reindex can only make the two agree — it
  writes no markdown and cannot lose work. It is therefore **on by default**; `DOCIR_WATCH=0`
  opts out, and `--no-daemon` runs never watch, so CI still runs the command explicitly.

  The debounce is not decoration: a `git checkout` rewrites hundreds of files, and this
  coalesces the burst into one rebuild. The watcher and the socket server share a single
  `SerializingExecutor`, because the server serializes clients while the watcher is a second
  writer and SQLite has exactly one. A failed rebuild is logged to `daemon.log` and the
  watcher keeps going — a half-written file is normal, and a thread that dies on it would
  leave a daemon that looks healthy and has silently stopped watching.
- **`docir get <id> --section "<heading>"`** — read one section instead of the whole body,
  the paired read for chunked ranking. `context` can now rank a document on one of its
  sections; without this the follow-up was still a 28,000-character body. It returns exactly
  the span `update --replace-section` would overwrite, so an agent cannot read one span and
  overwrite another. An unknown heading errors **listing the real ones**, because discovering
  them by fetching the whole body is the cost the flag exists to remove. Also on MCP as
  `docir_get(doc_id, section=...)`.
- **`benchmarks/run.py` reports semantic coverage** — how much of each body is inside a
  vector, with the model's window measured empirically rather than hardcoded. Coverage is the
  metric that describes this defect; recall cannot, because on a 26-document corpus FTS5
  rescues the rank either way. Recall is kept beside it as the no-regression gate, which
  matters: max-pooling over sections structurally favours documents with more of them.

### Fixed

- **`--append-section "## X"` wrote `## ## X` and said nothing.** The flag names a heading by
  its *text* and writes the `##` itself, so passing the line as it appears in the file doubled
  it. Nothing could then repair it: `--replace-section` keeps the heading line by contract,
  appending again adds a sibling, and `docir check` sees no problem — a doubled `#` is neither
  malformed frontmatter nor a graph fault. The only way out was `--replace-body --force`, so
  the *safest* body edit was the one that reached a state only the *riskiest* one could leave.
  Found when an agent composed the argument from a heading it had just read in a body, where
  it carries its `##`.

  A heading argument beginning with `#` is now refused at Tier 0, with an error naming the
  argument that works. Stripping the markers instead would look friendlier and be worse: it
  makes `"### Notes"` silently mean level 2, guessing at an intent the caller stated. A `#`
  *inside* the text still passes — `"C# interop"` is a real heading.

  `--replace-section` and `get --section` deliberately keep no such guard. Both match on
  heading text, so neither can corrupt — they fail rather than accept — and hand-editing
  markdown is permitted, so a file that already carries a doubled marker must stay readable
  or nobody can repair it. What they lacked was a message: `--replace-section` answered "no
  matching heading found" and left the caller guessing, and now shares one miss error with
  `get --section` that lists the real headings. The heading match and the section end boundary
  are one shared pair as a result, which is what the module's contract — read the same span
  you would overwrite — always claimed and two copies of a loop could not guarantee.

- **The daemon kept serving the code it started with, so a fix silently did not take
  effect.** The daemon loads docir once and lives on (900s idle timeout). Nothing compared
  the running process against the installed one, so after `uv sync`, a `pip install -U`, or
  any edit to `src/`, every command was answered by the old code — and the answer looked
  entirely normal. OBSERVED while fixing the cycle check above: `docir check` reported 117
  cycle findings and `docir --no-daemon check` reported 0, the difference being a daemon
  started before the edit. The plausible reading of 117 findings is that the fix is wrong.

  The pid file now records a **code stamp** — `__version__` plus the newest mtime across the
  package's sources — and `ensure_running` stops and replaces a daemon whose stamp is not the
  client's. The mtime half is what catches development: nothing bumps `__version__` between
  commits, so a source edit is invisible to a version comparison. An installed wheel stamps
  its files at install time, so the same pair moves on an upgrade. Recovery is automatic
  rather than something you have to suspect and fix with `docir daemon stop`.

  The stamp is computed once per process and frozen, which is what makes the daemon's answer
  honest: it reports the build it started with, not what is on disk now. `docir daemon
  status` prints that build (`serving 0.9.0`) and flags a stale one, so the state is
  inspectable rather than only inferable from an answer that looks wrong. A pid file written
  by an older docir holds a bare integer; its build is unknown, which never matches — that
  daemon is exactly the process the check exists to replace.

  `stop()` now waits for the process to actually exit. Its teardown clears the pid file and
  unlinks the socket, so a replacement spawned while it was winding down could have both
  removed out from under it, leaving a healthy daemon no client could find.

- **A mutually-referencing pair was reported as a cycle, permanently.** `check`'s cycle
  detection built its graph from every relation. `relates_to` — the default kind, and what a
  bare id in `related:` means — is symmetric: "A relates to B" and "B relates to A" are one
  statement written twice, so two documents that name each other are modelled correctly, not
  cyclically. `contradicts` is symmetric for the same reason.

  Measured on docir's own store: converting the corpus's prose cross-references into typed
  edges proposed 260 `relates_to` edges and took `docir check` from 0 findings to **127
  cycles**, none of them wrong. Keeping `check` readable meant dropping 120 correct edges
  instead. This is the defect the layering check's kind allowlist was introduced to end, one
  check over — a warning that fires on correct usage teaches people to ignore `check`, which
  is where the duplicate-id detection lives.

  A self-edge stays a cycle whatever its kind: symmetry is what makes a mutual pair legitimate
  and exactly what makes "A relates to A" empty, and `check` is the only thing that sees a
  self-edge a merge or a hand-edit wrote.


- **Most of a long document was not in the semantic index at all.** `bge-small-en-v1.5` reads
  about 512 tokens and silently ignores the rest — appending a sentence past that point
  returns a bit-identical vector, cosine 1.000000. Measured on real prose the window is
  ~1,900 characters, and **84 of the 103 documents in docir's own store exceed it**:
  corpus-wide, 44% of the text was inside a vector and 56% was not indexed semantically at
  all. The architecture document had 8% of itself embedded; the rule register had 5%. Those
  tails were not ranked badly, they were absent, and `docir context` returned a plausible
  answer every time.

  Full-text search hid it: FTS5 covers the whole body, so any query sharing vocabulary with
  a document found it and RRF pulled it to rank 1 regardless. The failure showed only on
  paraphrased queries against long documents — the case `docir context` exists for.

  docir now embeds **each section as well as the document** (ADR-0014). Coverage on its own
  store goes from **44% to 100%** (695 chunks over 103 documents), and on a real query —
  "how does the daemon keep the model warm" — the architecture document moves from rank 3
  with *no vector match* to rank 1 at similarity 0.696. Same corpus, chunking off vs on:
  recall@5 holds at 0.97 and **MRR rises 0.94 → 0.97**.

  Existing stores recompute on the next write or `docir embed --flush`; migration `0003`
  marks every embedding dirty so a store whose vectors already match the current model does
  not upgrade to zero chunks. The cost is ~7x more vectors, and `context` loads every active
  vector per call, so the practical corpus ceiling drops by about that factor.

- **`docir mcp serve` — the same commands, as MCP tools.** docir reached agents only through
  `docir agent install`, which teaches an assistant to run the CLI; a client that calls tools
  over the Model Context Protocol and never runs a shell could not use docir at all, which is
  most of them (Cursor, Codex, VS Code, ChatGPT, Claude Desktop). The server is built on the
  existing `Dispatcher` rather than beside it — every tool is one `Request` through a
  `RequestExecutor`, the same boundary the CLI and the daemon socket cross — so an MCP tool
  and its CLI command cannot answer differently. 19 tools, one per dispatcher command except
  the daemon's `ping`, plus a `docir_schema` tool for the one thing an agent needs that is not
  a command: the valid types, statuses and relation kinds it must write against.

  Details that are contract rather than convenience: reads return the same body-less
  skeletons (`docir_context` / `docir_search` / `docir_query`), only `docir_get` carries a
  body; every result goes through the same trimming the piped CLI's JSON does, so a tool
  result costs an agent what captured CLI output costs it; read tools carry `readOnlyHint`
  and `docir_delete` / `docir_tag_remove` carry `destructiveHint`; and requests go through
  the daemon by default, so one warm embedding model serves every call (`--no-daemon` holds
  a single in-process container instead).

  ```bash
  claude mcp add docir -- docir mcp serve   # stdio; --transport http also available
  ```

  `fastmcp` ships as a **default dependency**, not behind an extra. An extra would have been
  the smaller install, but it puts the discovery problem on the wrong side: an agent that only
  speaks MCP cannot be told to install the extra, because it cannot reach docir to be told.
  The stack is ~12 MB against onnxruntime's 68 MB, and it costs no startup time — `mcp/cmds.py`
  imports the server lazily, so only `docir mcp serve` pays fastmcp's ~0.3s import.

### Changed

- **docir's own documents no longer carry sequence labels.** Every document had two
  identifiers: its docir id, and a label in the title (`ADR-0015`, `GAP-056`, `FLOW-003`).
  Only the id addresses anything, so each prose citation of a label was a pointer both the
  reader and the tooling had to resolve by hand. 481 references across 94 documents became
  ids, 96 titles lost their label, and 97 files were renamed to match. Forty-nine of those
  titles were not names at all — they were the opening clause of the finding, cut at ~90
  characters, with the label doing the naming work — so each was rewritten. The provenance
  lines ("Migrated from the discovery gap register (GAP-0NN)") keep their labels: those record
  what a document used to be called, which is history rather than an address.


- **The `embeddings` extra is gone.** It was kept as a no-op alias after fastembed became a
  hard dependency in 0.8.0; `pip install docir[embeddings]` now warns about an unknown extra
  and installs the same thing it would have anyway. Nothing to migrate — plain
  `pip install docir` has included the embedding model since 0.8.0.

- **JSON trimming moved to `entry_points/payload.py`.** It was private to `cli/rendering.py`,
  and the MCP server needs the identical shape — an agent reading an absent field as "the
  default" must be able to do so whichever transport it came over. No behaviour change; the
  CLI's `--no-trim` still bypasses it.

## [0.9.0] - 2026-07-30

docir now maintains its own documentation in docir, and doing so found eight defects — every
one by running the tool against a real 101-document corpus rather than reading the code.

### Upgrade notes

- **Tag keys must match `^[a-z][a-z0-9-]*$`.** `docir tag add Auth` and
  `docir tag rename x Auth` now fail where they used to succeed, so a script that mints
  mixed-case or underscored keys needs updating. Keys **already in a registry are never
  rewritten** — no migration runs, nothing is lowercased for you. An existing key that
  fails the rule becomes a new `tag-key-format` *warning* from `docir check`, and the fix
  is `docir tag rename Auth auth`. `--strict` is unaffected.
- **A document may no longer relate to itself.** `docir update X --set-related X` is now a
  Tier 0 error. Self-edges already on disk are left alone and still surface as a `cycle`
  finding.
- **`docir lint --deep` reports less.** A `duplicate` is suppressed when the two documents
  are already linked, and a type can opt out of `scope-creep` with `max_body_chars`. If you
  were counting findings, the number moved for both reasons.

### Fixed

- **`docir lint --deep` no longer reports a duplicate for two documents you have linked.**
  The edge is the answer to "why are these similar" — the author has modelled the
  connection, which is what typed edges are for — so the finding left nothing to do but
  delete a document or unlink a correct relation. Measured against docir's own corpus, all
  14 duplicate findings were such pairs and the command drops from 21 findings to 8. An
  unlinked similar pair, the copy-paste the check exists to catch, is still reported.
- **`docir init` says so when it creates a store beneath an existing one.** Discovery walks
  up, so a nested `.docir` captures every command run under it — documents split across two
  corpora, with the outer store's `check` unable to see the inner ones at all — and nothing
  said a second store had been created or which one a write had landed in. `init` now warns
  on stderr and reports `enclosing_home` in its JSON. It warns rather than refuses: a
  monorepo subproject with its own store is legitimate, which is why `init` creates rather
  than reuses (ADR-0009). The fix is to the silence, not to the rule.
- **A document can no longer relate to itself.** `--set-related <self>` was accepted, and
  `docir check` then reported a one-node relation cycle — the write path manufacturing the
  finding the check path exists to report, clearable only by removing the edge again. Tier 0
  now refuses it on both write paths with `cannot relate document 'adr-…' to itself`,
  matching `cannot rename tag 't' to itself`: the same degenerate case, in a feature whose
  tests only ever used two different values. Self-edges already on disk are untouched and
  still surface as a `cycle` finding — the rule guards the write path, it does not rewrite
  anyone's files.
- **A transport failure is reported as an error, not a stack trace.** `runner.execute`
  wrapped only the *construction* of the executor in the handler that maps a `DocirError`
  onto its exit code; the dispatch call sat outside it. So every client-side daemon error —
  an unreachable daemon, one that would not start, a request that went unanswered — escaped
  Typer unhandled, printing a Python traceback and exiting 1 instead of the message and the
  exit code the error carries. `DOCIR_REQUEST_TIMEOUT=0.001 docir add` now prints
  `error: the daemon did not answer 'add' within 0.001s…` and exits 7. Errors the daemon
  *returns* were never affected, which is why this survived; a test pins that path too.
- **The benchmark measured a configuration nobody runs.** It built its store with the bare
  schema default (`sequential`, `adr-0007`) while `docir init` gives every real project
  `random` ids, so every token figure it had printed understated the shipped default by
  four characters per id. `docir context` is 464 tokens, not 448. Recall, precision and MRR
  are unaffected.
- **A command slower than five seconds no longer fails against the daemon.** The client
  set one socket timeout — `_CONNECT_TIMEOUT`, 5s — before connecting and left it in force
  for the reply, so the budget for reaching a local Unix socket also bounded however long
  the daemon took to do the work. `docir reindex` over a 65-document store died with
  `daemon socket error: timed out` at 5s while the daemon completed the rebuild in ~10s.
  Connect and reply are now timed separately: connect keeps the 5s budget, the reply gets
  `request_timeout` (300s, settable with `DOCIR_REQUEST_TIMEOUT`).
- **A timed-out request is no longer resent.** `SocketExecutor` treated every `DaemonError`
  as a stale socket: it killed the daemon and replayed the request. Combined with the bug
  above, any write slower than 5s was executed, reported as failed, and then executed a
  second time against a daemon killed mid-transaction — for `add`, a duplicate document.
  A reply timeout now raises `DaemonTimeoutError`, which is never retried and names the
  escapes (`docir daemon status`, `DOCIR_REQUEST_TIMEOUT`, `--no-daemon`).

### Added

- **The benchmark prices the random-id entropy.** A random id is ~3× a sequential one and
  appears in every skeleton and every `related` edge of every result, but nothing measured
  the trade, so 48 bits had been chosen by default rather than deliberately.
  `benchmarks/run.py` now reports id characters per result set against their sequential
  equivalent, alongside a collision table by suffix length. **48 bits stays**: random ids
  cost 3.4% of a `context` payload, while dropping to 32 bits would return about 1% of it
  and buy a 1.16% chance of a duplicate id by ten thousand documents — the exact failure
  `docir check --strict` exists to catch at merge time.
- **Tag keys have a format rule.** Any non-empty string was a valid key, so `auth`, `Auth`
  and `authentication` could all exist and nothing objected — while document ids were
  strictly regex-validated by contrast. `tag add` and `tag rename` now require
  `^[a-z][a-z0-9-]*$` and reject anything else. Keys already in a registry are **never**
  rewritten: silently lowercasing someone's key is a rewrite of their data, so an existing
  non-conforming key is a new `tag-key-format` **warning** from `docir check` instead, and
  the fix is `docir tag rename Auth auth`. `rename` validates only the new key, since
  renaming away from a legacy key is the migration path. The rule stays a warning
  deliberately — a `--strict` build must not fail for a key its author could not have
  avoided.
- **A type can set its own `lint --deep` size limit.** The `scope-creep` heuristic used one
  character threshold for every type, so a glossary, a rule register and a probe log were
  permanently "too long" — and a register split in half is two half-registers, so the advice
  could not be taken. `max_body_chars` is now a per-type schema key alongside `review_days`:
  absent inherits the default (8000), `0` means never. Combined with the duplicate fix,
  `lint --deep` over docir's own corpus drops from 21 findings to 4.
- **`docir tag list` reports a usage count per tag.** The registry could only grow: nothing
  distinguished a tag holding the vocabulary together from one no document has carried since
  it was coined. Each entry now carries `usage`, the number of indexed documents holding the
  tag. Archived documents count, because that is the set `tag rm` blocks on — a tag reported
  as dead that then demanded `--force` would be worse than no count at all. `0` therefore
  means `tag rm` will take it without a flag, and a zero survives JSON trimming.
- **CI gates document integrity.** `docir check --strict` runs after the test suite, failing
  the build on `error` findings — duplicate ids and dangling edges, which is what a branch
  merge introduces. It announces a skip when no project store is committed rather than
  exiting 0 silently, so a passing gate cannot be confused with an unchecked corpus.

### Documentation

- **docir now maintains its own documentation in docir.** A project-local store at `.docir/`
  holds 93 documents: the 11 ADRs, the two architecture documents, two runbooks, the five
  flow documents and the frame/actors/rules/glossary/probe-log registers from the discovery
  bundle, plus the 50 gap findings and 17 clarifying questions as `issue` documents. Ids are
  random, so each document keeps its `ADR-00NN` / `GAP-0NN` / `Q-0NN` / `FLOW-00N` number in
  its title and [`docs/README.md`](docs/README.md) maps every pre-migration path to its id.
  `docs/adr/`, the four loose `docs/*.md` files and `analysis/` are gone — each verified
  present in the store field-by-field first.
- **A `reference` type** is added inline in `docs-schema.yaml` for descriptive registers (a
  glossary, an actor catalog, a rule register). They record what *is*, so they are `active`
  until superseded. `level: 5` matches `architecture`, because reference material is what
  everything else is written against and the layering check warns on a document that
  `depends_on`/`refines` something of a lower level.
- Prose citations became typed edges — each gap links to its flow and, where an executed
  probe proved it, to the probe log; each question links to its gap. That took `docir check`
  from 25 orphan warnings to zero findings.

## [0.8.0] - 2026-07-29

Pagination on the list paths, UTC dates, and the scope of full-text search stated where
people will look for it.

### Upgrade note

**Dates are now stamped in UTC.** If you work well east or west of UTC, a document created
near midnight will carry the UTC calendar date rather than your local one. Dates already in
your files are untouched — they are the source of truth and are read as written.

### Added

- **`--limit` / `--offset` on the list paths.** `docir query` and `docir search` take both, and
  `docir tag list` — which had no window at all — now pages too. `query`'s window is a SQL
  `LIMIT`/`OFFSET`: it previously fetched every match and sliced in Python, so the cost of a
  page grew with the corpus behind it. A page shorter than `--limit` means the end; there is no
  total, because the response is a bare JSON array with nowhere to put one.
  Two predicates cannot use a SQL window and page over the filtered set instead: `--stale`
  (derived from the clock and the type's cadence) and `search`'s status filter (FTS5 cannot see
  a status). A window applied in SQL there would count rows *scanned* rather than rows returned.

### Changed

- **Dates are UTC.** `created`, `updated` and `verified` used the writer's local date, so two
  teammates either side of midnight stamped different dates for the same moment — in files that
  are committed and read by other people. `docir` has no released users' data to migrate, so
  existing dates are simply reinterpreted.
- **User-facing prose says "store"** where it said "data root"; `--home` keeps its name.

### Documentation

- **Search covers title, description and body — not tags**, now stated in the README and the
  agent guide. Tags are a controlled vocabulary for `query --tag`, deliberately out of the
  full-text index so one tag match cannot flood out the text matches.
- **Recovering from `unknown-type`** is documented: re-enable the profile or change the type,
  then reindex. `check --fix` will not guess which you meant.
- **A "Scope and limits" section** in the README, naming what is bounded and what is not —
  `context` loads every current embedding per call, which sets the practical corpus ceiling,
  and `lint --deep` is O(n²) over those vectors.

## [0.7.1] - 2026-07-29

All fixes, three of them found by a delta analysis pass over the surface 0.7.0 itself added —
two were introduced by 0.7.0's own features.

### Upgrade note

**`docir init` now honours `--home`.** It previously ignored the flag and created the store
under the current directory. If a script passed `--home` to `init`, the store moves to where
the flag says. Passing `--home` *and* a project directory is now an error rather than a
silent preference, since they disagree about where the store goes.

### Fixed

- **`docir init` honours `--home`.** It computed its store from the positional directory
  alone, so `docir --home /srv/docs init` silently created `<cwd>/.docir` instead — the flag
  whose purpose is choosing the store location was the one command that ignored it. `--home`
  now names the store directly; passing it *and* a project directory is refused, since they
  disagree about where the store goes.
- **`docir init --force-schema` works without `--force`.** The more specific flag was a
  silent no-op on its own.
- **Read commands warn about an accidental global store too.** The warning was wired only to
  writes; `query`/`search`/`context`/`get` now share it, so "am I reading the corpus I think
  I am?" is answered on stderr rather than by a field repeated on every row.
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

- **Semantic embeddings are on by default** (ADR-0011, now `docir get adr-ab9c454b760c`).
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

[Unreleased]: https://github.com/l0kifs/docir/compare/v0.22.0...HEAD
[0.22.0]: https://github.com/l0kifs/docir/compare/v0.21.0...v0.22.0
[0.21.0]: https://github.com/l0kifs/docir/compare/v0.20.0...v0.21.0
[0.20.0]: https://github.com/l0kifs/docir/compare/v0.19.0...v0.20.0
[0.19.0]: https://github.com/l0kifs/docir/compare/v0.18.0...v0.19.0
[0.18.0]: https://github.com/l0kifs/docir/compare/v0.17.0...v0.18.0
[0.17.0]: https://github.com/l0kifs/docir/compare/v0.16.0...v0.17.0
[0.16.0]: https://github.com/l0kifs/docir/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/l0kifs/docir/compare/v0.14.0...v0.15.0
[0.14.0]: https://github.com/l0kifs/docir/compare/v0.13.1...v0.14.0
[0.13.1]: https://github.com/l0kifs/docir/compare/v0.13.0...v0.13.1
[0.13.0]: https://github.com/l0kifs/docir/compare/v0.12.0...v0.13.0
[0.12.0]: https://github.com/l0kifs/docir/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/l0kifs/docir/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/l0kifs/docir/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/l0kifs/docir/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/l0kifs/docir/compare/v0.7.1...v0.8.0
[0.7.1]: https://github.com/l0kifs/docir/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/l0kifs/docir/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/l0kifs/docir/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/l0kifs/docir/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/l0kifs/docir/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/l0kifs/docir/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/l0kifs/docir/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/l0kifs/docir/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/l0kifs/docir/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/l0kifs/docir/releases/tag/v0.1.0
