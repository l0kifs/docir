---
paths:
  - "src/docir/platform/filesystem/code_matcher.py"
  - "src/docir/platform/clock/**"
  - "src/docir/modules/documents/domain/services/graph_checks.py"
  - "src/docir/modules/documents/application/services/maintenance_service.py"
---

# Staleness — the calendar and the evidence

Staleness is the one trust signal the product offers, so the rules protect the clock rather than the reporting.

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
