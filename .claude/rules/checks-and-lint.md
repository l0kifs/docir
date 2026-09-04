---
paths:
  - "src/docir/modules/documents/domain/services/graph_checks.py"
  - "src/docir/modules/documents/domain/services/validation.py"
  - "src/docir/modules/documents/domain/services/similarity_lint.py"
  - "src/docir/modules/documents/application/services/maintenance_service.py"
  - "src/docir/modules/documents/application/services/schema_conformance.py"
  - "src/docir/entry_points/doctor.py"
---

# Validation tiers, check, lint and doctor

Three tiers, and mixing them is the documented overengineering trap. The recurring mistake is promoting a warning to an error: each one below red-builds a *correct* repository, which is how a merge gate gets deleted and takes duplicate-id detection with it.

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

- **Tier 1 findings carry a severity, and `--strict` gates on `error` only.** `ERROR_KINDS`
  (`graph_checks.py`) is `duplicate-id`/`dangling`/`malformed` — the corpus is *broken* — plus
  **`empty-index`**, which earns the severity by a different argument: it means `check` could
  not *look*. The graph half reads the index, so with none built every structural finding is
  silent and `--strict` exits 0 — a merge gate that passes by reading nothing, green on a
  corpus with sixteen dangling edges (issue-87410666c867). The warnings below all red-build a
  *correct* setup; this red-builds one that was never checking anything. The bootstrap
  (adr-e53c813d2f13) takes the ordinary fresh checkout out of its reach, leaving the stores
  that bootstrap never saw: files that landed after the container was built, or an index left
  by a docir predating it. It fires only when
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
  **`orphan` reads the authored graph only, and is closed by an edge or by `isolated:`**
  (adr-e98749aa457d). It used to read the derived mention graph too, which made it
  self-clearing: an orphan triage is a list of orphan ids, so writing the diagnosis closed
  every id it diagnosed. `isolated:` is the recorded exemption — free text saying why the
  document is *meant* to stand alone, skipped by this check and by nothing else, audited with
  `docir query --expr "isolated"`. `--fix` must neither grant nor withdraw one.
  **The last three carry a sharper version of the same argument and must not be promoted**: the
  schema they measure against ships in the *package* (the core and the profiles are merged in on
  every command), so a corpus that passed yesterday can fail today with no commit to point at.
  An error kind there red-builds every repo on the release that moved the rule, and nothing about
  the documents changed.

- **`missing-required` is the one Tier 1 finding a hand-edit is not needed to produce.** Its
  siblings (`unknown-type`/`unknown-status`/`unknown-tag`/`unknown-relation-kind`) all mean a file
  was written outside the CLI; this one means the *rule* moved under documents that were valid
  when written. It reads only the type's declared `required_fields` — a core required field is
  what makes a document parse, so an absent one is already `malformed` — and it shares
  `validation.is_absent` with Tier 0 rather than restating "empty", because the two disagreeing
  would let `check` call a document conforming that the next write refuses.

- **`docir check --fix` (`MaintenanceService.repair`) is the only sanctioned recovery path.**
  Detection without repair forced the user into hand-editing markdown — the one thing thesis #2
  forbids. It repairs exactly what needs no guess: duplicate ids (re-issued; the *oldest* file
  keeps the id, because existing edges were written against it and an edge cannot say which
  document it meant) and dangling edges (dropped). `malformed`/`unknown-type` are deliberately
  left unrepaired and returned in `RepairResult.remaining` — each needs somebody to read the
  file and decide what it should say, and a repair has nothing to read *with*. It reindexes first — id allocation
  consults the index for a free number — and does **not** advance `updated`, since a mechanical
  repair is not a re-verification (that would launder the staleness clock).

- **The schema can change without anyone editing it, and Tier 1 says so (issue-d891ab5501e6).**
  The core and the bundled profiles are YAML strings compiled into `infra/profiles.py` and
  re-merged by `_merge_profiled` on *every* command, so upgrading docir can add a type, make a
  field `required:`, or change a prefix in a store whose `docs-schema.yaml` nobody touched —
  nothing in `git diff` to review. The index therefore records the resolved schema it was last
  rebuilt against (`schema_baseline`, migration `0005`, one row) and `check` reports the
  difference as `schema-drift`, one finding per change. Three rules hold it up:
  **a rebuild is the only writer of that baseline** — `reindex`, and the store bootstrap that
  shares its transaction (`MaintenanceService._rebuild`), never a third path (it is already the
  "make derived state agree with the sources" verb; an `accept` command would be a ritual whose
  only effect is silencing a report — the argument adr-bd7c4f3c5764 makes about staleness);
  **absent means unknown, not
  unchanged**, so a store with no baseline reports nothing rather than reporting its whole schema
  as new (an unparseable one reads the same way, since `reindex` overwrites it); and the payload
  is rendered by `domain/services/schema_shape.describe`, which `infra`'s `describe_schema`
  delegates to — the drift check lives in `application`, which may not import `infra`, and a
  second renderer would mean a baseline written in one shape and compared in another.
  `DOCIR_SCHEMA_NOTICE=1` additionally prints the drift on stderr after every command; it is
  emitted **client-side** through the same `RequestExecutor`, because with the daemon the process
  that first loads a changed schema is the daemon, whose stderr is a log nobody reads.

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
  finding kinds, and the split now runs along severity. `no-index` is a **warning** in the
  past tense — doctor's own dispatch is one of the things that repairs it, so an error would
  gate on a store that is already fine, the argument `stale-daemon` settled
  (adr-e53c813d2f13). `empty-index` keeps **error**, since the reads there still answer
  nothing. A partial mismatch stays
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
