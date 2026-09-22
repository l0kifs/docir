---
created: '2026-07-30'
description: 'The executed probes behind the gap register: what was run, what came
  back, and what it proved.'
id: ref-1509d5dbb4c3
owner: maintainer
related:
- arch-1cfb1b212237
- adr-90e994d931cc
- adr-ab9c454b760c
- issue-0ff355fa21dd
- issue-9ed4905e0db8
- issue-b4f441c7210f
- issue-cc61d038cf8f
- issue-d7767bef9399
- issue-f01a7a585fc1
- issue-f6a5d0b86806
- issue-0783d236d565
- issue-20933967697b
- issue-389dc5dac58a
- issue-476b4e188fab
- issue-5bfbc6f2699d
- issue-638068ed09a6
- issue-7e16dfe2521c
- issue-8c37bf22ba3c
- issue-93152f7b9213
- issue-9417ffd5306d
- issue-96b03701503b
- issue-996b567e5131
- issue-9bbca6c0f434
- issue-9cb85759076d
- issue-b47a1203baa2
- issue-b7ddde3ce860
- issue-b8220546282c
- issue-be95d3e242a3
- issue-c2b4e38e76d9
- issue-e183d47cdee1
- issue-ed49c1d03894
- issue-fd547a293d01
status: active
tags:
- docs
- testing
title: Discovery probe log — PROBE-1..N and the delta pass
type: reference
updated: '2026-09-22'
---

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
than measured. Recorded as `issue-e183d47cdee1`.

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

Checklist items that produced findings: bulk import/export (issue-20933967697b), merge/deduplicate
(issue-cc61d038cf8f), delete + compensating action (issue-fd547a293d01), every-state-has-an-exit (issue-b47a1203baa2), concurrent
transition by two actors (issue-389dc5dac58a, issue-be95d3e242a3), duplicate submission / idempotency (issue-389dc5dac58a),
admin override + audit (issue-0783d236d565), support diagnosis tooling (issue-476b4e188fab), notifications (issue-b4f441c7210f),
time/timezone (issue-7e16dfe2521c), volume limits (issue-f6a5d0b86806), observability (issue-e183d47cdee1), migration of data
created under older rules (issue-ed49c1d03894).

Checklist items examined and found **adequately covered** (recorded so coverage is not
overstated): create validation (BR-001..BR-005), read visibility (BR-028, BR-029), field
mutability by state (BR-005), transfer of ownership (`--set-owner`), retention (git holds
history), permissions (N/A per adr-90e994d931cc), rounding/currency/tax (no money in this domain).

Smell scan (`gap-checklists.md` §3, automated regex over all 45 rule statements): **0 hits**.

## PHASE 7 — adversarial self-review

Ran against my own register, not the code. Four defects found and fixed:

```
SELF-1  GAP-013 was hedged ("advanced and committed... or not"). Re-read repositories.py —
        next_number only *flushes*, so the counter rolls back with the transaction while the
        already-written file survives. Rewritten as a concrete third duplicate-id path.
SELF-2  GAP-012 was severity:material but meets my own blocking rubric ("touches data loss").
        Raised to blocking; register re-sorted.
SELF-3  BR-034 has four conditions and no decision table — violates quality gate §9.
        Table added (verified against runner.py).
SELF-4  Q/BR/GAP cross-references were inconsistent after renumbering. Reconciled by script;
        verified no dangling or undefined ids in either direction.
```

Claims I attempted to refute and could **not**: issue-b7ddde3ce860, issue-8c37bf22ba3c, issue-996b567e5131, issue-9cb85759076d, issue-389dc5dac58a,
issue-b47a1203baa2, issue-93152f7b9213, issue-b8220546282c — each is reproducible by the probe recorded above.

Claim I did refute and narrowed: an early reading that `docir context --limit` overflows in
every case. PROBE-4 (`--limit 1` → 1 result) shows it overflows only when selected documents
have outgoing edges to documents not already selected. issue-996b567e5131 states that actual condition.

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
DELTA-PROBE-1  docir --home X init            → store created in CWD, X untouched   issue-638068ed09a6
DELTA-PROBE-2  init --force-schema (no --force) → silent no-op                      issue-9417ffd5306d
DELTA-PROBE-3  store field on read paths      → absent on query/search/context      issue-c2b4e38e76d9
DELTA-PROBE-4  query --stale --include-archived → correct; archived excluded by default — NO gap
DELTA-PROBE-5  check --fix with unknown-tag   → correctly returned in `remaining`  — NO gap
DELTA-PROBE-6  tag rename X X --merge         → registry entry deleted, docs keep the tag  issue-9bbca6c0f434
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

## About the analysis/ paths in this log

This document was `analysis/99-log.md` until the discovery bundle was folded into docir's own store. The `analysis/...` paths in the text above describe where the run wrote its output at the time; those files are documents in this store now — see `docs/README.md` for the map. The gap issues that cite this log link to it as a typed edge.
