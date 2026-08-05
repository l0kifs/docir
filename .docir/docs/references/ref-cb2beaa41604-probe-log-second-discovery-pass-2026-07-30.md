---
created: '2026-07-30'
description: What was executed against the CLI in the 0.8.0+ pass, what it returned,
  and the four areas deliberately not reached.
id: ref-cb2beaa41604
owner: maintainer
related:
- ref-0f48dc93d435
- ref-1509d5dbb4c3
- adr-ab9c454b760c
- issue-b8220546282c
- issue-b928ad676595
- ref-32cb4f874fbe
status: active
tags:
- docs
- testing
title: Probe log — second discovery pass, 2026-07-30
type: reference
updated: '2026-08-05'
---

Every probe below was executed against a throwaway store built by `docir init`, with
`DOCIR_EMBEDDER=deterministic` unless stated. Frame: `ref-0f48dc93d435`. Predecessor log
(v0.2.1): `ref-1509d5dbb4c3`.

## Daemon transport and lifecycle — unexamined by the previous pass

```
PROBE-D1  daemon start / status                         serves, reports pid + socket   — NO gap
PROBE-D2  SIGKILL the daemon, leave stale pid + socket  next `add` respawns, exit 0    — NO gap
PROBE-D3  two stores side by side                       one socket each, no cross-talk — NO gap
PROBE-D4  DOCIR_REQUEST_TIMEOUT=0.001 on a write        Python traceback, exit 1         GAP-052
PROBE-D5  `daemon stop` after SIGKILL                   reports stopped, status clean  — NO gap
PROBE-D6  900 KB body over the socket                   round-trips byte-exact         — NO gap
```

D2 and D6 are worth stating positively, because both are load-bearing claims nobody had
executed: the daemon really is disposable — a `kill -9` leaves a stale pid file and a stale
socket, and the next command respawns through them without the user seeing anything — and
the length-prefixed framing really does survive a payload far larger than one socket read,
which is the reason it is length-prefixed rather than newline-delimited.

D4 is the finding. The message the client raises is correct and names its escape hatches;
it is never rendered, because `runner.execute` wraps only the *construction* of the
executor in the handler that maps a `DocirError` onto its exit code, and the dispatch call
sits outside it.

## Embedding scheduler

```
PROBE-E1  `embed --flush` with nothing dirty            {"embedded":0}, idempotent     — NO gap
PROBE-E2  read the store under a different embedder     similarity absent, no error      confirms ADR-0011
PROBE-E3  `add --wait-embeddings`                       exit 0, vector present         — NO gap
```

E2 is the behaviour adr-ab9c454b760c promises and is worth pinning here: switching `DOCIR_EMBEDDER`
does **not** raise `dimension mismatch`. The foreign-model vectors are ignored, `context`
returns rows with `similarity` absent rather than zero — absent meaning "no current vector",
which is why `--min-score` does not filter them — and `embed --flush` recomputes both
documents, after which similarity is present again. Verified in both directions.

## Reads, schema and adoption

```
PROBE-R1  --offset 99 / --offset -1                     0 rows / exit 2 with a message — NO gap
PROBE-R2  --limit 0 / --limit -3                        exit 2 with a message          — NO gap
PROBE-R3  --set-related <self>                          accepted; check reports a cycle  GAP-053
PROBE-R5  `lint --deep` on a small corpus               exit 0, no findings            — NO gap (smoke only)
PROBE-R6  agent install x2, update, update on nothing   idempotent; `[]` when nothing  — NO gap
PROBE-R7  `init` inside an existing store's tree        nested store, silent            GAP-054
PROBE-R8  switch the schema profile with docs present   `unknown-type` x2, left in
                                                        `check --fix` remaining        — NO gap
```

R8 confirms the documented behaviour exactly: disabling a profile that has documents leaves
them with a type the schema no longer knows, `check` reports `unknown-type`, and `--fix`
declines to guess and returns them in `remaining`. The first attempt at this probe was
wrong and is recorded because the correction matters: it used `decision` documents, which
are in the frozen **core** and therefore survive any profile change. Only a profile-owned
type (`issue`, `architecture`) demonstrates the case.

R6: `docir agent update` with nothing installed returns `[]` and exits 0. Recorded and
judged **not** a gap — an empty result is the honest answer, and unlike issue-b8220546282c's silent
no-op on a *typo*, nothing here was mistyped. Noted so the judgement is visible rather than
assumed.

## What this pass did NOT examine

- **Alembic migrations.** Probing the upgrade path needs a store pinned at an older
  revision, which nothing in the repo produces. Fresh-store migration runs on every probe
  above and works; upgrade-from-old is untested here and was untested by the previous pass.
- **`lint --deep` beyond a smoke test.** Its O(n²) similarity comparison and its scope-creep
  heuristic were not exercised on a corpus large enough to say anything.
- **The 38 `assumed` rules** in `ref-32cb4f874fbe`. Out of scope by decision: re-deriving
  them from the same code produces the same assumptions. They need a human who can say what
  was intended — the finding archived issue issue-b928ad676595 records.
- **The ranking constants.** `benchmarks/` measures them; reasoning about them here would
  add nothing.

## What the pass suggests about where defects live

All three findings are in the seam between a component and its caller, not inside either:
an exception that crosses the transport boundary and lands outside the handler; a write
path that produces the state the check path reports; a store-creation rule that is correct
in isolation and silent about its neighbour. The previous pass reached the same conclusion
from a different direction — "a feature added to close a gap is new surface, and its
degenerate cases are unexamined by construction". Degenerate cases at boundaries is where
to look next.

## Third round, 2026-07-30 — the two areas the pass skipped

The second round listed Alembic's upgrade path and `lint --deep` as not reached. Both were then reached.

## Alembic — no defect, and thesis #1 demonstrated end to end

```
PROBE-A1  a fresh store reports revision 0002, relations carry `kind`   — NO gap
PROBE-A2  walk the store back to 0001, run any command                  upgrades to 0002, exit 0
PROBE-A3  what the dropped columns cost                                 owner, verified and the
                                                                        edge kind come back empty
PROBE-A4  `docir reindex`                                              restores all three from
                                                                        the files; check clean
```

The upgrade fires automatically on the next command and needs no user action. A2-A4 are the important pair read together: dropping the columns loses the values, and `reindex` puts every one of them back — owner `platform-team`, verified `2026-07-30`, and the `supersedes` kind that had reverted to the `relates_to` server default — because the markdown files are canonical and the index is a projection. That is the product's first thesis, executed rather than asserted, and nobody had run it before.

Read A3 carefully and do NOT record it as data loss: the downgrade is artificial. A real 0001 store predates typed edges and staleness entirely, so its edges *were* all `relates_to` and it had no owner or verified to lose — the server defaults migration 0002 chooses are exactly right for the data that actually exists at that revision. The loss here was manufactured by downgrading a store that already held 0002 data, which no user can do.

Also observed: there is **no `alembic.ini`**. `run_migrations` builds the config in Python and points `script_location` at `Path(__file__).parent / "alembic"`, so alembic cannot be driven against a store by hand (`alembic current`, `alembic history`, `alembic downgrade`). Recorded and judged **not** a gap: a second declaration of the script location is exactly the drift the programmatic resolution exists to prevent, and the recovery story for this product is `reindex`, not hand-run migrations.

## lint --deep — two findings

```
PROBE-L1  `lint --deep` over the 99-document store    21 findings in 5.2s
          14 `duplicate`, every pair already linked                        GAP-055
          7 `scope-creep`, 5 of them reference registers                   GAP-056
```

The runtime is worth recording: 5.2 seconds for the O(n²) comparison over 99 documents, which is well inside anything a person would notice, and the first number available for the ceiling the README warns about.

Both findings are the same shape as defects this project has already fixed once — a heuristic that fires on correct usage (`orphan` under `--strict`, the layering exemption list). Every one of the 21 findings against the product's own corpus is unactionable, which makes `lint --deep` a command nobody runs twice.

## Still not reached

The 38 `assumed` rules and the ranking constants, unchanged from the second round and for the same reasons.
