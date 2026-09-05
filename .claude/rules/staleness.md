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

- **A verification does not outlive what it covered (adr-f4e6ade4afd0).** The trigger is
  `content_changed` — the same three fields that queue a re-embed, and nothing else, because
  everything a write can otherwise touch leaves the reviewed text exactly as it was and a
  `status` is the first thing to move on a document somebody just finished reviewing. The
  write erases `verified` and stamps `revoked`, and `--verified` in the same call outranks
  it. `--clear-verified` is a *different* write, not the same one asked for by hand
  (issue-b4813930bfca): it leaves no `revoked` at all, so the document ages from `created`.
  An edit earns a restarted cadence because something true stopped being true; a withdrawal
  earns none, or taking back a stamp that had nearly run out would push the due date further
  away than leaving the wrong stamp in place. The cadence then
  restarts **from the revocation**: ageing a revoked document from `created` reports it
  overdue the instant the edit lands on any corpus older than its cadence, which is
  adr-fad49eaa4648's own measurement arriving on the other clock. **Only a *standing*
  verification is revoked**, and that is the load-bearing half — the automatic path skips a
  document carrying none, and the flag is *refused* rather than idempotent, because a stamp
  granted against no review is a fresh cadence bought by typing: issue-6726eabcf871 through
  the new field. One verification buys one reset.

- **`verified_content` catches the edits the write path cannot see.** `--verified` digests the
  title/description/body it covered — hashed from the document the write *produces*, so
  verifying alongside a rewrite records the rewrite — and `check` raises
  `verification-outdated` wherever the two disagree: a hand-edit, a merge resolved into the
  body, or a teammate on a build that predates revocation. The predicate is the digest and
  **not** `verified < updated`, which was the obvious one and is unusable — a status or a tag
  moves `updated` without touching a reviewed word, so it fires on the ordinary life of a
  correctly verified document (issue-40d1792bc9f9's shape). Empty means *unknown*, so every
  stamp older than the field is silent; both withdrawal paths clear it, since a digest under no
  claim is evidence of nothing. A warning with two exits, a fresh `--verified` or a
  `--clear-verified`, both judgements — so `check --fix` leaves it, exactly as for
  `code-changed`.

- The `verified_code` digests are **kept**:
  they answer "has the code moved since somebody read this", which is exactly what is open on
  a document whose calendar just reset — what adr-d9e6d5ccd0b4 forbids is an old digest under
  a *fresh* `verified`, not one under none.

- **The clock runs from `verified`, else `revoked`, else `created` — never `updated` (adr-fad49eaa4648).**
  The fallback has to be a date an edit cannot move, or the queue clears itself the moment
  anybody reads it: writing a re-check into an overdue document took it out of
  `query --stale`, and a re-check is the one edit an unanswered document reliably gets, so
  the longer something went unanswered the more certainly it disappeared
  (issue-6726eabcf871). `created` is the only date the write path sets once and never
  rewrites. This is issue-9ed4905e0db8 one level out — that issue stopped `tag rename`
  advancing `updated` because a bulk edit forged the clock; *every* edit forged it.
  **Absent `verified` is not infinitely stale**, which was the other candidate and was
  measured before it was rejected: on this store it reports 83 of 84 cadence-bearing
  documents, ones written the day before included, and makes `review_days` inert for every
  unverified document — issue-40d1792bc9f9's shape, a warning that fires on the product's
  own defaults. The `stale` finding names which clock it read, because a reader who edited
  the document yesterday will otherwise read the finding as a bug.

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
