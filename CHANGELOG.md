# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/l0kifs/docir/compare/v0.12.0...HEAD
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
