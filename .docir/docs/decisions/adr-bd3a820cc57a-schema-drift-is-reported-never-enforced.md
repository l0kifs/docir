---
code:
- src/docir/modules/documents/domain/services/schema_shape.py
- src/docir/modules/documents/application/services/maintenance_service.py
- src/docir/platform/persistence/alembic/versions/0005_schema_baseline.py
created: '2026-08-08'
description: Why a store records the resolved schema it was built against, why reindex
  is the only thing that advances it, and why the finding is a warning that must never
  become an error.
id: adr-bd3a820cc57a
owner: maintainer
related:
- kind: refines
  to: adr-2a3f625bb2f8
- adr-bd7c4f3c5764
- issue-d891ab5501e6
- issue-8f6576cd7bc9
- issue-0e3d1d9c81d3
- issue-3678c897295f
status: accepted
tags:
- schema
- integrity
- cli
title: Schema drift is reported, never enforced
type: decision
updated: '2026-08-08'
---

## Context

A store's grammar is not the file it appears to be in. `docs-schema.yaml` names *profiles*; the
frozen core and each named profile are YAML strings compiled into `infra/profiles.py`, and
`_merge_profiled` resolves `core -> profiles -> inline` on every command. So the types, statuses,
cadences and relation kinds a store enforces are supplied by the installed docir as much as by the
file the user committed.

That is what makes the schema evolve without a schema migration, and until 2026-08-07 nothing in
the system acknowledged it. Six change classes were measured against real stores (issue-8f6576cd7bc9,
issue-d891ab5501e6): a removed type surfaced as `unknown-type`, a removed status as `unknown-status`,
a new `required:` entry as *nothing at all* until an unrelated write was refused, a changed prefix
and a dropped relation kind as nothing ever. Every one of them arrives with no local edit and
nothing in `git diff` to review — and where a consequence *was* reported, the cause was not, so the
findings read as if they came from nowhere.

The obvious moves were all available and all wrong for this project: a `schema_version:` key (it is
hand-edited, so it drifts from what the file says, and it describes the file while the change comes
from the package), document auto-migration, and pinning a store to a docir version.

## Decision

**Drift is reported, never enforced, and the baseline is derived state advanced by `reindex`.**

Four parts:

1. **The index records the resolved schema it was last rebuilt against** (`schema_baseline`,
   migration `0005`, one row) — the *merged* result, not the file, because the merged result is
   what validation enforces. It is derived like every other table here: `reindex` rebuilds it, it
   is gitignored with the rest of the index, and it is never a second thing a hand-editor has to
   keep in sync.

2. **`docir check` reports the difference as `schema-drift`, one finding per change**, in the terms
   of the file: `+type test_plan`, `type decision: required [] -> ['owner']`. The lines *are* the
   product — the change arrived without a diff to read, and this is that diff.

3. **`reindex` is the only writer of the baseline.** It is already the "make derived state agree
   with the sources" verb. A `docir schema accept` was considered and rejected: its only effect is
   to silence a report, which is the acknowledgement ritual adr-bd7c4f3c5764 argued against for
   staleness — a nag a bot can clear is not a human dealing with the change.

4. **Warning severity, and it must stay one.** `--strict` gates on `error` and this is not damage:
   the documents are untouched and the *rule* moved. An error kind red-builds every repository on
   the release that moved it. The same argument governs the two findings shipped beside it
   (`missing-required`, `unknown-relation-kind`), which describe rules documents no longer satisfy
   rather than documents that are broken.

**Absent means unknown, not unchanged.** A store with no baseline reports nothing, rather than
reporting its whole schema as newly added — the rule `similarity` and `code_matches` already
follow, and the one that keeps an upgrade quiet on first contact.

## Consequences

- **Easier:** the question "what did this upgrade change about my schema, and which of my documents
  does it break" has an answer, from `check`, before anyone runs into it document by document.
  `unknown-type` and `missing-required` now arrive with their cause stated next to them.
- **Harder:** there is one more piece of derived state, and one more thing `reindex` is responsible
  for. A store that is never reindexed never gets a baseline and so never reports drift — correct
  (nothing to compare against) but easy to misread as "no drift".
- **`describe_schema` moved from `infra` to `domain/services/schema_shape`,** with the infra name
  delegating. The drift check lives in `application`, which the module rules forbid from importing
  `infra`; a second renderer would mean a baseline written in one shape and compared in another.
  `docir schema show` and the `docir_schema` MCP tool are unchanged.
- **`DOCIR_SCHEMA_NOTICE=1` is the escape hatch for the case `check` cannot cover** — a change
  nobody will run `check` to discover. Off by default, because a notice on every command until
  someone reindexes is how a warning stops being read. It is emitted client-side through the same
  `RequestExecutor` as everything else: with the daemon, the process that first loads a changed
  schema is the daemon, whose stderr is a log nobody reads.
- **What this does not do, deliberately:** it does not migrate documents. Every change class needs a
  human decision — which status replaces the removed one, who owns a newly-required field — and
  guessing is exactly what `check --fix` already refuses to do for `unknown-type`. Drift tells you
  what moved; dealing with it is yours.
- **Still open:** nothing renders the effect of a `docs-schema.yaml` edit *before* it lands
  (issue-3678c897295f). That would mean reading git objects, which docir has never done.
