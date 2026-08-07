---
code:
- src/docir/modules/documents/domain/services/schema_shape.py
- src/docir/modules/documents/application/services/maintenance_service.py
- src/docir/platform/persistence/alembic/versions/0005_schema_baseline.py
- tests/modules/documents/test_schema_shape.py
created: '2026-08-07'
description: docs-schema.yaml has no version and the index records nothing about the
  schema it was built against, so a release editing the core or a profile changes
  what every store enforces with no local edit and no report.
id: issue-d891ab5501e6
owner: maintainer
related:
- issue-8f6576cd7bc9
- adr-2a3f625bb2f8
status: resolved
tags:
- material
- schema
title: A store cannot tell that its schema changed under it on upgrade
type: issue
updated: '2026-08-07'
---

**Class:** missing · **Severity:** material
**Source:** schema-evolution investigation, 2026-08-07 (sibling of issue-8f6576cd7bc9)
**Step:** upgrading docir · **Frequency:** every release that touches the core or a profile

## Finding

A store cannot tell that its schema changed. `docs-schema.yaml` carries no version, the index
records nothing about the schema it was built against, and no command compares the two — so a
release that edits the frozen core or a bundled profile changes what every existing store
enforces, silently, with no local edit to review and nothing in any output that says so.

The change arrives through the package, not the file. `CORE_SCHEMA_YAML` and `PROFILE_YAMLS` are
YAML strings compiled into `infra/profiles.py`, and `_merge_profiled` (`schema_loader.py:121`)
re-resolves `core -> profiles -> inline` on **every command**. A store whose file says
`profiles: [software]` therefore picks up a new type, a new `required:` entry, a changed status
graph or a changed cadence the moment docir is upgraded. `git diff` on the store shows nothing:
the file did not change, its meaning did.

## What happens today

The measured consequences, one per change class (throwaway stores, `--no-daemon`):

| the release changes | what the store does | first report |
|---|---|---|
| a field becomes `required:` | nothing | an unrelated `update` fails — issue-8f6576cd7bc9 |
| a type is removed | `unknown-type` warning | `update`/`add` of that type; only `archive` still works |
| a status is removed | `unknown-status` warning; the doc **reappears in default reads**, because the status left every `inactive_statuses` | a transition out of it, needing `--status X --override` |
| a prefix changes | nothing | never — `issue-0001` and `bug-0001` coexist permanently |
| a relation kind is dropped | nothing | only a rewrite of that edge |
| the *loader* gets stricter | **every command exits 3** — `get`, `query`, `check`, `reindex`, `schema validate`; only `version` runs | immediately |

The last row is the shipped precedent, not a hypothetical: 0.10.0 made `required:` names validate
at load, and its own upgrade note has to explain by hand what a schema author will see.

Nothing bridges the gap. `docir schema show` prints the merged result, but there is no baseline to
compare it against. `docir check` sees documents, never the schema's own history. `docir init
--force` compares the file byte-for-byte against what the *current* release would generate
(`composition.py:313`), so a store scaffolded by an older docir — whose generated header text has
since changed — reads as "customised" and is preserved with a warning, even untouched. The
CHANGELOG's "Upgrade notes" section is the entire migration channel, and it is prose.

## Impact

The one file the docs tell you to edit by hand is the one file whose meaning can change without
you editing it. There is no way to answer "what did this upgrade change about my schema?" or
"which of my documents does that break?" before running into it document by document. For a store
that is committed and shared, the person who hits the failure is usually not the person who
upgraded.

## Proposed default

Record the **resolved** schema (the merged result, not the file) as a fingerprint in the index at
startup, and report a change the next time it moves — kind `schema-drift`, warning severity,
naming what moved: `+required decision.owner`, `-type release_note`, `prefix issue: issue -> bug`.
Warning, not error, for the reason `unknown-type` is one: nothing is broken, the schema simply no
longer matches what the corpus was written against, and failing CI for a store that was valid the
day before is how the `--strict` gate became unusable the first time.

The fingerprint belongs in the index rather than the file: it is derived state, `reindex` can
rebuild it, and it must not become a second thing a hand-editor has to keep in sync.

Deliberately not proposed:

- **A `schema_version:` key in `docs-schema.yaml`.** It is hand-edited, so it would drift from
  what the file actually says, and it describes the *file* while the change comes from the package.
- **Auto-migrating documents.** Every change class above needs a decision — which status replaces
  the removed one, who owns a newly-required field — and guessing is the error `check --fix`
  already refuses to make for `unknown-type`.
- **Pinning a store to a docir version.** That trades a silent change for a hard stop and leaves
  the corpus behind on an old release.

## Actors affected

- ACT-002 repository maintainer / developer

## Evidence

- `src/docir/modules/documents/infra/schema_loader.py:121` — `_merge_profiled`, re-resolved per command
- `src/docir/modules/documents/infra/profiles.py` — core + profiles compiled into the package
- `src/docir/entry_points/composition.py:313` — `--force` refreshes only a byte-identical file
- `src/docir/platform/persistence/alembic/versions/` — migrations `0001`–`0004` cover the index only
- `CHANGELOG.md:16` — "Upgrade notes" as the only migration channel

## Resolution

FIXED 2026-08-07, as proposed. The index records the resolved schema it was last rebuilt against
(`schema_baseline`, migration `0005`, one row) and `check` reports the difference as
`schema-drift` — one finding per change, in the terms of the file: `+type test_plan`,
`type decision: required [] -> ['owner']`, `type issue: prefix 'issue' -> 'bug'`.

Three scoping decisions:

- **Reported by `check` by default**, with `DOCIR_SCHEMA_NOTICE=1` additionally printing the
  drift on stderr after every command. Off by default because a notice that repeats on every
  command until someone reindexes is how a warning stops being read; on for the change nobody
  will run `check` to discover. The notice is emitted **client-side**, as one more request
  through the same `RequestExecutor` — with the daemon, the process that first loads a changed
  schema is the daemon, whose stderr is a log nobody reads.
- **The full rendering is stored, not a hash**, which is what makes a diff possible at all. A
  hash could only say that something moved.
- **`reindex` is the only writer of the baseline** — already the "make derived state agree with
  the sources" command. A `schema accept` verb was rejected: its only effect is to silence a
  report, which is the ritual adr-bd7c4f3c5764 argued against for staleness.

A store with no baseline reports nothing: absent means unknown, not unchanged, so an upgrade does
not report the whole schema as newly added. A baseline that will not parse reads the same way —
it is derived state, and `reindex` overwrites it.

One structural consequence worth recording: `describe_schema` moved from `infra` into
`domain/services/schema_shape.py`, with the infra name delegating. The drift check lives in
`application`, which the module rules forbid from importing `infra`, and a second renderer for
the second caller would have meant a baseline written in one shape and compared in another.
`docir schema show` and the `docir_schema` MCP tool are unchanged.

Verified by injecting three bugs: making the notice unconditional, treating an absent baseline as
empty, and stopping `reindex` from recording it. Each was caught by a different test.
