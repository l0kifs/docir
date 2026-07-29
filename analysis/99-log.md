# Run log — append-only

## PHASE 0/1 — frame + evidence inventory

```
2026-07-26  FRAME       README.md, CLAUDE.md, docs/adr/*        → 00-frame.md written
2026-07-26  INVENTORY   evidence ranking below
```

### Evidence available (ranked per extraction.md §1)

| Rank | Source | Available? | Notes |
|---|---|---|---|
| 1 | Production behaviour / user work | **NO** | No telemetry in product; no user access this session |
| 2 | Code, DB schema, migrations | **YES** | 105 files / 6 919 LOC; alembic 0001+0002 |
| 3 | Tests (acceptance/E2E) | **YES** | 28 test files incl. `tests/entry_points/test_e2e_*.py` |
| 4 | Config, flags, jobs | **YES** | `pyproject.toml`, env vars (`DOCIR_*`), daemon idle timer, embedding scheduler |
| 5 | Tickets, logs, analytics | **NO** | GitHub issues not fetched (non-interactive); no logging of business events |
| 6 | SME statements | **NO** | Single maintainer, not interviewed |
| 7 | Written docs | **YES, treated as claims** | README, CLAUDE.md, 10 ADRs, 4 CONTRACT.md, CHANGELOG, `docs/AGENT_GUIDE.md` |

**Consequence:** the two highest-value evidence ranks (1, 5) are missing entirely. Every
"frequency" and "actual impact" statement in `05-gaps.yaml` is therefore `unknown` rather
than measured. Recorded as `GAP-001`.

## PHASE 2 — extraction

```
2026-07-26  P1 struct   entry_points/cli/app.py, dispatch.py      → 27 CLI commands, 18 wire commands
2026-07-26  P1 struct   alembic/versions/0001,0002                → 7 tables + 1 FTS5 virtual table
2026-07-26  P1 struct   documents/domain/{schema,entities,vo}     → Document aggregate, Schema, DocId, RelatedRef
2026-07-26  P1 struct   documents/infra/{profiles,default_schema} → core + 5 profiles, 12 types
2026-07-26  P2/P3       documents/application/services/*          → DocumentService, MaintenanceService call chains
2026-07-26  P2/P3       tags/application, indexing/*, agents/*    → per-module behaviour + ordering
2026-07-26  P2/P3       platform/{persistence,filesystem,transport}, entry_points/daemon
2026-07-26  P4/P5       all of the above                          → BR-001..BR-072 drafted
2026-07-26  READ        tests/** (28 files)                       → cross-check of P4; encoded intent
2026-07-26  SKIPPED     tach.toml, scripts/check_contract_sync.py → out of scope per 00-frame.md
2026-07-26  SKIPPED     assets/, docs/PUBLISHING.md, .github/     → out of scope per 00-frame.md
2026-07-26  SKIPPED     platform/persistence/alembic/env.py       → migration machinery, no business rule
```

### Empirical probes (evidence rank 1-substitute: executed the real CLI)

Store fixtures under the session scratchpad; all runs `--no-daemon`, real SQLite, real files.

```
PROBE-1  clone->reindex->add    store1  → CONFIRMED id collision (GAP-003)
PROBE-2  get/query after PROBE-1 store1 → CONFIRMED first doc invisible to all read paths
PROBE-3  check --strict on 2 new docs   → exit 1 from `orphan` alone (GAP-006)
PROBE-4  context w/ resolved neighbour  → CONFIRMED inactive filter bypassed via graph (GAP-004)
PROBE-5  context --limit 3, 3x out-deg 2 → returned 9 docs (GAP-005)
PROBE-6  delete --force w/ incoming ref  → CONFIRMED dangling ref written to canonical file (GAP-007)
PROBE-7  update a doc holding dangling ref → CONFIRMED accepted, ref re-persisted (GAP-007)
PROBE-8  decision --related issue        → CONFIRMED permanent `layering` warning (GAP-008)
PROBE-9  delete then add                 → id NOT reused (counter monotonic) — no gap
```

```
2026-07-26  PROBE-10  6x concurrent --no-daemon add   → all returned adr-0002 (GAP-009)
2026-07-26  PROBE-11  same race WITH the daemon        → adr-0002..0007, unique — scopes GAP-009
2026-07-26  PROBE-12  schema validate on a typo'd transition target → {"valid":true} (GAP-010)
2026-07-26  PROBE-13  agent install --agent <typo>     → [], exit 0, no files (GAP-024)
2026-07-26  PROBE-14  context on unrelated query       → returns a doc, score 0.0328 (GAP-017)
2026-07-26  PROBE-15  all five profiles merged         → 15 types, no prefix collision — NO gap
2026-07-26  PROBE-16  delete then add                  → id not reused — NO gap
```

## PHASE 3/4 — modeling + formalizing

```
2026-07-26  MODEL   01-actors.yaml     → 8 actors (2 of them absent-but-implied: ACT-007, ACT-008)
2026-07-26  MODEL   02-flows/          → 5 flows, 41 hotspots, 3 off-system step clusters
2026-07-26  MODEL   04-glossary.yaml   → 13 terms, 10 with recorded conflicts
2026-07-26  FORMAL  03-rules.yaml      → 45 rules (EARS), 3 decision tables, 5 marked `disputed`
```

## PHASE 5 — gap detection

Coverage checklists from `gap-checklists.md` §2 iterated mechanically against every flow and
the `document` / `tag` entities. Result: **39 gaps** — 6 blocking, 20 material, 13 cosmetic.

Checklist items that produced findings: bulk import/export (GAP-036), merge/deduplicate
(GAP-028), delete + compensating action (GAP-007), every-state-has-an-exit (GAP-010), concurrent
transition by two actors (GAP-009, GAP-037), duplicate submission / idempotency (GAP-009),
admin override + audit (GAP-014), support diagnosis tooling (GAP-012), notifications (GAP-011),
time/timezone (GAP-038), volume limits (GAP-039), observability (GAP-001), migration of data
created under older rules (GAP-025).

Checklist items examined and found **adequately covered** (recorded so coverage is not
overstated): create validation (BR-001..BR-005), read visibility (BR-028, BR-029), field
mutability by state (BR-005), transfer of ownership (`--set-owner`), retention (git holds
history), permissions (N/A per ADR-0003), rounding/currency/tax (no money in this domain).

Smell scan (`gap-checklists.md` §3, automated regex over all 45 rule statements): **0 hits**.

## PHASE 7 — adversarial self-review

Ran against my own register, not the code. Four defects found and fixed:

```
SELF-1  GAP-013 was hedged ("advanced and committed... or not"). Re-read repositories.py:55 —
        next_number only *flushes*, so the counter rolls back with the transaction while the
        already-written file survives. Rewritten as a concrete third duplicate-id path.
SELF-2  GAP-012 was severity:material but meets my own blocking rubric ("touches data loss").
        Raised to blocking; register re-sorted.
SELF-3  BR-034 has four conditions and no decision table — violates quality gate §9.
        Table added (verified against runner.py:36-48).
SELF-4  Q/BR/GAP cross-references were inconsistent after renumbering. Reconciled by script;
        verified no dangling or undefined ids in either direction.
```

Claims I attempted to refute and could **not**: GAP-003, GAP-004, GAP-005, GAP-006, GAP-009,
GAP-010, GAP-017, GAP-024 — each is reproducible by the probe recorded above.

Claim I did refute and narrowed: an early reading that `docir context --limit` overflows in
every case. PROBE-4 (`--limit 1` → 1 result) shows it overflows only when selected documents
have outgoing edges to documents not already selected. GAP-005 states that actual condition.

## Quality gates (SKILL.md §9)

```
[x] Every actor appears in >=1 flow                     8/8
[x] Every flow has unwanted-behaviour rules per failure point
                                    BR-001..003, 010..012, 018, 043, 061, 064, 070, 071
[x] Every rule has an evidence pointer and a status     45/45 (verified by script)
[x] Every rule with >2 conditions has a decision table  BR-003, BR-005, BR-034
[x] Smell scan clean                                    0 hits across 45 statements
[x] Every glossary term has exactly one definition      13 terms; 10 conflicts recorded as gaps
[x] Every hotspot resolved into a rule/gap/assumption   41/41
[x] Coverage log lists what was not examined            below
[x] Adversarial pass run and findings addressed         4 found, 4 fixed
```

## Coverage report — what was NOT examined

**Not examined at all** (out of scope per `00-frame.md`, or no business rule inside):
`tach.toml`, `scripts/check_contract_sync.py`, `.github/workflows/`, `assets/`,
`docs/PUBLISHING.md`, `pyproject.toml` packaging metadata,
`platform/persistence/alembic/env.py`, `platform/embedding/fastembed.py` (optional dependency,
excluded from the project's own type-check and coverage).

**Examined shallowly** (read for structure, not line-by-line; rules here are lower-confidence):
`platform/transport/{protocol,client,messages}.py`, `entry_points/daemon/socket_executor.py`,
`entry_points/cli/{body_input,rendering}.py` beyond the trim logic,
`modules/agents/{domain,infra}/**` beyond the service, `modules/agents/infra/templates/skill.md`.

**Evidence classes entirely unavailable this run** (see `00-frame.md`): production behaviour,
support tickets, logs, analytics, and any SME statement. Ranks 1, 5 and 6 of the evidence
hierarchy are absent — which is why `frequency` is `unknown` on almost every gap and why every
rule is `status: assumed` rather than `confirmed`.

**Consequence for the reader:** this register is a *draft* until the maintainer confirms it.
An agent-produced rule register is not valid elicitation until the source agrees with it
(`questioning.md` §5).

## Follow-up session — fixes and their consequences (2026-07-26)

Implemented at the maintainer's direction, each verified against the real CLI before the
gap record was closed.

```
FIX  GAP-003  reindex restores the id counter; + IdGenerator skips indexed ids;
              + create refuses to overwrite a file already holding the id   → resolved
FIX  GAP-013  same change; a crash mid-write can no longer be overwritten silently → resolved
FIX  GAP-009  next_number is one atomic upsert (was read-modify-write in Python);
              busy_timeout set explicitly                                    → resolved
FIX  GAP-005  --limit is a hard ceiling; --expand N reserves neighbour slots,
              unused ones backfilled; expansion breadth-first across seeds    → resolved
NEW  --id-style on `docir init`, defaulting to `random` (BR-073, BR-074)
DOC  packaged agent guide corrected: `docir reindex --all` does not exist     → GAP-040
```

Attribution was tested, not assumed: each fix was reverted in isolation and the new tests
re-run, to confirm they fail against the old behaviour (`assert 9 == 3` for GAP-005;
8 concurrent adds colliding for GAP-009).

### Findings produced BY these changes

```
GAP-040  the shipped agent guide told agents to run a flag that does not exist; nothing
         validates the template against the CLI. Typo fixed, guard still missing.
GAP-041  the counter restore reads an all-digit random id (0.36% of them) as sequential.
         Latent: no symptom while the type stays `random`.
GAP-042  random ids are ~3x longer and ride in every skeleton and every edge; the token
         cost of the new default is unmeasured (see GAP-001).
```

Rules restated rather than left stale: BR-006 (id allocation is style-dependent, not
counter-only) and BR-007 (uniqueness) move `disputed` → `confirmed`. BR-073/BR-074 added for
schema-wide `id_style` inheritance and the `init` default.

**Blocking gaps still open: GAP-006, GAP-012, GAP-001.**

```
FIX  GAP-041  counter restore now keyed on the schema's declared id_style, with a
              suffix-length guard for ids left behind by a style switch      → resolved
```

```
FIX  GAP-006  CheckIssue carries a severity derived from its kind; --strict gates on
              errors only; --strict-all preserves fail-on-anything            → resolved
              NOTE: the existing test asserted the old behaviour as intent, so the tests
              could never have caught this — only running the tool did.
```

```
FIX  GAP-012  `docir check --fix` re-issues duplicate ids (oldest keeps it) and drops
              dead edges; malformed/unknown-type returned as needing a human  → resolved
              GAP-007 becomes recoverable but is still not prevented — stays open.
NEW  found while testing: `_as_list` accepted only `list`, but `dataclasses.asdict`
     preserves tuple fields, so the table renderer showed "nothing to repair" while
     --json printed the fix. Caught only because the human path was exercised
     separately from the JSON one. Both are now asserted in the same test.
```

**Blocking gaps still open: GAP-001 only** (nothing measures whether docir works).

```
FIX  GAP-001  benchmarks/ — 20-doc corpus, 12 judged tasks, recall/precision/MRR +
              payload size per strategy, run against both embedders        → resolved
NEW  GAP-043  the measurement's own headline: the DEFAULT embedder is lexical, not
              semantic, so `context` ~= `search` unless the `embeddings` extra is on.
              README:42 claims "retrieval by meaning" for a config most users lack.
```

Measured (2026-07-26, 20 docs / 12 tasks, recall@5):
`context` 0.88 default vs 0.96 fastembed · `search` 0.85 both · graph expansion +0.07 under
both · `context` 430 tokens vs 3 240 to read every body (7.5x).

```
FIX  GAP-043  docs-honesty pass: README table, command table, agent guide and CLAUDE.md
              now say which configuration each retrieval claim describes. No code
              change — the code was right, the copy was not.               → resolved
              OPEN QUESTION deferred: should fastembed be the default? Left undecided;
              it is a dependency-weight call, not a correctness one.
```

```
FIX  GAP-043  fastembed is now a hard dependency and the default; the hashing embedder
              becomes the DOCIR_EMBEDDER=deterministic fallback. README states the
              measured cost (~64 MB model, ~240 MB deps) instead of a caveat. → resolved
NEW  GAP-044  found while implementing that flip: nothing recorded which model produced
              a vector, and mismatched widths RAISE. The switch would have broken every
              existing store on first `docir context`. model_id is now written and
              honoured; foreign vectors fall out of ranking and are recomputed. → resolved
```

## Follow-up — verifying the default flip outside this machine (2026-07-27)

```
CHECK  uv.lock in sync with the new required dependency, committed  → clean
CHECK  CI workflow                                                  → passes, but see below
NEW    GAP-045: the default embedder path was excluded from every gate (ty, coverage,
       no tests) while CI installed 240 MB and ran none of it. The exclusions were
       correct when the adapter was opt-in and became a hole when it became the
       default; nothing re-checks an exclusion when its premise changes. → resolved
       Lifting the ty exclusion surfaced a real diagnostic on the first run.
```

```
FIX  GAP-036  `docir import` adopts existing markdown and preserves the number the
              filename implies, so historical cross-references survive adoption.
              Verified on docir's own ADR corpus.                          → resolved
              Two of my own test expectations were wrong, not the code: a title of
              "2026 is the year..." must NOT be de-numbered (only a number followed
              by punctuation is a label), and asdict returns tuples, not lists.
```

```
FIX  import now reports skipped files. Found by pointing it at `analysis/`: 12 files in,
     7 imported, 5 dropped with no mention — including 05-gaps.yaml and 06-questions.yaml.
     My own test had asserted non-markdown was *ignored*, never that it was *reported*.
```

```
FIX  GAP-004  one `_is_visible` predicate now serves both `context` paths; the ranked
     GAP-019  loop and graph expansion can no longer filter differently. Expansion also
              follows incoming supersedes/contradicts, successors first.       → resolved
              Maintainer answered Q-005 "hidden" (not "returned but flagged") and Q-017
              "yes, follow it backwards".
```

Attribution tested, not assumed: each half was reverted in isolation and only its own test
failed (`_is_visible` → the resolved-neighbour leak; the incoming lookup → the backwards
successor). The third test, the `--include-resolved` escape hatch, passed under both reverts,
which is what makes it an independent check rather than a restatement of the first.

### Findings produced BY these changes

```
GAP-046  the benchmark cannot see either fix. Both change retrieval semantics; every
         number was byte-identical either side (recall@5 0.96 fastembed / 0.88
         deterministic). corpus.yaml has no supersedes edge and no inactive document,
         so the two behaviours `context` most depends on are unmeasurable. The corpus
         was deliberately NOT edited: re-basing it would break comparability with every
         figure recorded before today, and that is the maintainer's call.
NEW      benchmarks/run.py printed `embedder: deterministic (default)` from
         os.environ.get(..., "deterministic (default)") — a label, not the resolved
         object. The default flipped to fastembed in ADR-0011 and this line did not,
         so every run since has reported a configuration it did not measure. It was
         reporting "deterministic" while scoring 0.96, the recorded fastembed figure.
         `Container` now carries the built embedder and the harness prints its model_id.
```

The shape is GAP-045's again, one layer up: a default changed and the thing describing it
did not. There it was a test exclusion; here it was the measurement's own header — inside
the harness built to settle GAP-043, which was itself a docs-honesty gap.

```
FIX  GAP-046  corpus re-based to 23 docs / 14 tasks: a supersedes-linked decision pair
              plus a resolved issue. Loader learned typed edges and `status_path`.
              The harness now moves under these fixes.                     → resolved
              Measured by reverting each fix against the new corpus:
              context recall@5 0.93 -> 0.96 (fastembed), 0.89 -> 0.93 (deterministic).
```

**A conclusion this re-base weakened, recorded rather than buried.** ADR-0011's headline
number — `context` 0.96 with the model vs 0.88 without — becomes 0.96 vs 0.93 on the new
corpus, because the two new tasks depend on the relation graph and graph expansion helps
both embedders equally. The ADR's decision still holds, but the evidence for it had to move:
at `--expand 0`, which isolates the ranking from the graph, the hashing embedder scores
0.80 against plain `search`'s 0.83 — it ranks *below* the lexical index it is meant to be
complementing — while the model scores 0.87. README, CLAUDE.md and benchmarks/README.md now
quote that pair and say why. Re-basing a benchmark can invalidate the argument the previous
baseline was built to support; the fix is to re-derive the argument, not to keep the corpus
that flattered it.

```
FIX  GAP-008  layering check reads a dependency allowlist (`depends_on`, `refines`)
              instead of exempting supersedes/contradicts. `relates_to` — every bare
              id — no longer violates. PROBE-8 replayed: `[]` where it reported a
              permanent violation; `:depends_on` on the same edge still flags. → resolved
              Q-006 implemented on its recorded assumption, not on an answer.
```

Third instance of the same trap, now worth naming: `test_layering_violation` built a
default-kind edge and asserted a violation, so the suite encoded the defect as intent and
could never have caught it. GAP-006 had it (`test_check_strict_gates_ci` asserted the
unusable gate), GAP-045 had it in a different form (an exclusion whose premise had
expired). In all three the defect was found by running the tool and reading the output as a
user would, never by reading or running the tests. A test written from the implementation
tests that the implementation is itself; only a test written from the intended behaviour can
disagree with the code.

`_SUCCESSOR_KINDS` and the layering set have now diverged, as the GAP-019 comment predicted
they should be free to: `{supersedes, contradicts}` and `{depends_on, refines}` share
nothing. Keeping them separate cost one duplicated frozenset and avoided coupling two
unrelated rules through a shared constant.

## Follow-up — the shipped guide is now checked against the CLI (2026-07-28)

```
FIX  GAP-040  test_agent_guide_matches_cli.py resolves every `docir ...` in the
              packaged guide against the Typer command tree. 29 invocations.
              Attribution: three defects injected (unknown flag, unknown
              subcommand, unknown top-level command), each caught.      → resolved
REWORD        the guide said "One `docir import`-style bulk pass" — a backticked
              command that deliberately does not exist. Prose, not an exemption:
              an agent runs a backticked command whatever the sentence says.
```

**The guard shipped broken twice before it worked, and neither defect was visible by
reading it.** First: the inline-span regex paired backticks across the whole document, but a
``` fence *is* backticks — every fenced block collapsed into one giant "span" and shifted
every pair after it. It reported a healthy-looking 28 invocations and did not contain the one
line the test exists to catch; the injected `reindex --all` passed. Second: after fixing
that, an unknown word fell back to the parent group, so `docir schema dump` validated
against `docir schema`.

Both were found the same way — by injecting the bug the test claims to catch and watching it
pass. A test written against a real corpus that happens to be clean cannot distinguish
"nothing is wrong" from "nothing is checked".

The guard-the-guard has the same disease in miniature: it first asserted `len(INVOCATIONS)
>= 20`, which both defects satisfied. A count cannot say *which* line went missing. It now
names six invocations that must be found, each reachable from a different part of the
document — fenced block, inline span, table cell, indented sub-list.

This is the fourth appearance of the family recorded here (GAP-006, GAP-045, GAP-008, now
GAP-040), and the sharpest: the other three were tests that asserted existing behaviour was
intended. This one asserted nothing at all while appearing to assert a great deal.

## Follow-up — forced delete compensates for what it breaks (2026-07-28)

```
FIX  GAP-007  `delete --force` strips the edge from every referencing document in
              the same transaction and reports them ("deleted X; unlinked from Y").
              PROBE-6/PROBE-7 replayed: file reads `related: []`, no dangling
              finding, a later `update` has nothing to re-persist.      → resolved
              Deviates from the proposed `tag rm --force` pattern on one point:
              `updated` is NOT advanced. Copying it wholesale would have
              reproduced GAP-020, which is open against the tag path for exactly
              that. Follows `check --fix` instead.
```

**The fix invalidated five tests, and that is the interesting part.** Each used `delete
--force` as a cheap way to *manufacture* a dangling edge before asserting something about
`check` or `check --fix`. That route is now closed, so they build the state the way it
actually occurs: remove the target's file as a merge from a branch that deleted it would,
then reindex.

`test_check_detects_dangling_reference` in `test_merge_safety.py` is the one worth naming.
Its comment already claimed to simulate "a cross-branch delete after a merge" — but it used
the CLI shortcut, so the merge-safety test was not exercising a merge. The comment described
the intent and the code did something easier; nothing flagged the divergence because the
assertion still passed. A convenience path used as a fixture had quietly become the thing
under test.

GAP-007 moves from *recoverable* to *prevented*. `check --fix` stays as the recovery path
for edges broken outside the CLI — which, after this, is the only way left to break one.

```
NEW      05-gaps.yaml GAP-001 carried a duplicate `resolution:` key, and five entries in
         06-questions.yaml (Q-002/003/004/007/012) carried duplicate `answered`/`authority`/
         `answer` keys with the trailing copy set to null. YAML keeps the last key, so the
         primary deliverable parsed with four answered BLOCKING questions reading as
         unanswered and GAP-001's resolution reading as absent. Only the prose was ever
         read; nothing parsed these files. Duplicates removed, `answered_note` folded into
         `answer`; both files now round-trip through yaml.safe_load with the intended values.
```

```
REVERT GAP-036  `docir import` built, then removed the same day, before committing.
       Two reasons: random-ids-by-default removes its only unique capability, and it
       reported `imported 2, failed 0` over a file holding three decisions (one
       superseded, one rejected) plus a file whose body said "DRAFT — do not rely on
       this". A command that makes adoption look finished is worse than no command.
       GAP-036 returns to OPEN; the reasoning is recorded there so it is not rebuilt
       naively. The agent guide now carries the review-then-add workflow instead.
```

## DELTA PASS — 2026-07-29, v0.7.0 (39 commits since the original run at 560aea5)

Scope: the surface *added or changed* since v0.2.1, not a re-derivation. The existing
register was appended to, never rewritten (SKILL.md §1.6). 37 of 46 recorded gaps had been
resolved; the question was what the fixing itself introduced.

```
FRAME    delta only: 34 source files changed, +1951/-265; 8 new CLI flags
INVENTORY same evidence ranks as the original run — 1, 5 and 6 still absent
EXTRACT  P1 via the Typer command tree (authoritative, not the docs)
DETECT   7 empirical probes against the real CLI, listed below
```

### Probes

```
DELTA-PROBE-1  docir --home X init            → store created in CWD, X untouched   GAP-047
DELTA-PROBE-2  init --force-schema (no --force) → silent no-op                      GAP-049
DELTA-PROBE-3  store field on read paths      → absent on query/search/context      GAP-050
DELTA-PROBE-4  query --stale --include-archived → correct; archived excluded by default — NO gap
DELTA-PROBE-5  check --fix with unknown-tag   → correctly returned in `remaining`  — NO gap
DELTA-PROBE-6  tag rename X X --merge         → registry entry deleted, docs keep the tag  GAP-048
DELTA-PROBE-7  add --id in a random store     → adopted; next id still random      — NO gap
```

Three of seven probes found nothing. Recorded so the coverage is not overstated: the
stale/archived interaction, `check --fix`'s handling of the new finding kinds, and
cross-style id adoption are all correct.

### What the delta pass was for

**Two of the four findings were introduced by the fixes themselves**, which is the argument
for running one at all:

- GAP-048 (self-merge corrupts the registry) came from the GAP-028 merge, four commits
  earlier. Its tests asked "does merging two tags work?" and never "what if they are the
  same tag?". It shipped in 0.7.0 and manufactured precisely the `unknown-tag` state that
  the GAP-016 work had taught `check` to detect — one fix creating the condition another
  fix had just learned to report.
- GAP-050 came from the GAP-023 fix, which reasoned about writes and did not ask whether
  reads have the same question. GAP-049 came from the GAP-026 fix.

**A feature added to close a gap is new surface, and its degenerate cases are unexamined by
construction** — the tests written alongside it are shaped by the gap it was closing.

GAP-047 is different: it predates the original run and that run missed it. `init` is the one
command that builds its own home rather than using the resolved settings, so it fell outside
a review that traced `Settings.resolve`. Worth remembering that "every command does X" is a
claim to verify per command, not per resolver.

### Coverage — what this pass did NOT examine

Unchanged since v0.2.1 and not re-read: the daemon transport and lifecycle, the embedding
scheduler, `lint --deep`, the agents module beyond the template, and Alembic. The nine
cosmetic gaps left open from the original run were not re-examined either; they were
assessed for priority on 2026-07-29 (see the entries) but not re-derived from code.
