---
code:
- src/docir/modules/documents/domain/services/graph_checks.py
- src/docir/modules/documents/domain/services/validation.py
- tests/modules/documents/test_domain_services.py
- tests/modules/documents/test_integration_maintenance.py
created: '2026-08-07'
description: Adding 'required:' to a live type leaves every existing document in violation
  with no finding of any kind; the first report is an unrelated update failing, one
  document at a time.
id: issue-8f6576cd7bc9
owner: maintainer
related:
- issue-e3c4dfad4f7b
- adr-2a3f625bb2f8
- issue-d891ab5501e6
- issue-0e3d1d9c81d3
status: resolved
tags:
- material
- schema
title: A newly-required field is invisible to docir check, and surfaces one write
  at a time
type: issue
updated: '2026-08-07'
---

**Class:** missing · **Severity:** material
**Source:** schema-evolution investigation, 2026-08-07 (what happens when a release changes `docs-schema.yaml`)
**Step:** upgrading docir, or adding `required:` to a live type · **Frequency:** every time a required field is added to a type that already has documents

## Finding

Adding a `required:` field to a type that already has documents leaves every existing document
in violation, and **nothing reports it**. `docir check` returns clean; the corpus looks healthy.
The violation surfaces only when someone next writes to one of those documents — one document at
a time, at an unrelated moment, as a hard write failure.

Reproduced in a throwaway store: a `decision` document written without an owner, then
`required: [owner]` added to the type.

```
docir check       -> only 'orphan' findings; nothing about the missing field
docir reindex     -> documents_indexed: 2, documents_skipped: 0
docir get <id>    -> full document, no flag of any kind
docir update <id> --set-title "Renamed"
                  -> error: required field 'owner' is missing or empty for type 'decision'
```

The failing command asked to change the *title*. `update` validates the whole merged document
(`document_service.py:206`), which is right — but it means an unrelated patch is where the
schema change is announced.

## What happens today

This is the one schema-change class with no detection. The two beside it both have a Tier 1
finding, added for exactly this reason — the document is still readable, the schema simply no
longer describes how it is classified:

| the schema change | what `docir check` says |
|---|---|
| a type is removed (profile disabled) | `unknown-type` warning (`graph_checks.py:268`) |
| a status is removed from a type | `unknown-status` warning (`graph_checks.py:169`) |
| **a field becomes required** | **nothing** |

`GraphChecker.check` (`graph_checks.py:92`) never consults `required_fields`, and
`Tier0Validator.validate_required_fields` (`validation.py:35`) is reachable only from the two
write paths (`document_service.py:158`, `:206`).

The gap widens with how a schema change actually arrives. Core and profile types are YAML
strings compiled into the package (`profiles.py`), re-merged on every command, so a store whose
`docs-schema.yaml` says `profiles: [software]` picks up a new `required:` entry **on upgrade,
with no local edit and no notification**. The person who has to satisfy it never saw it change.

## Impact

The corpus is silently non-conforming and the only way to find out is to write to every document.
There is no way to answer "which documents does this schema change break?" — not before an
upgrade, not after, not in CI. `docir check --strict` is green throughout, so a merge gate
reports a corpus that no longer satisfies its own schema.

This is the same shape as issue-e3c4dfad4f7b, one level up: there, an unsatisfiable `required:`
name was reported at the write instead of at the load, and the fix moved it to where the author
could act on it. Here the schema is satisfiable and the *documents* are the ones that do not
satisfy it, with no equivalent place to find that out.

## Proposed default

A Tier 1 `missing-required` finding: for each document, the type's `required_fields` that are
absent or empty, named per document. Warning severity, alongside `unknown-type` and
`unknown-status` — the document is readable and every edge resolves, and promoting it to `error`
would fail CI for a corpus that was valid the day before the upgrade, which is how the `--strict`
gate became unusable the first time. `--strict-all` still covers anyone who wants it fatal.

That also makes the recovery queryable rather than discovered: `check`, fix the named documents
with `docir update <id> --owner ...`, done.

Deliberately not proposed:

- **Blocking the schema load.** The schema is satisfiable; refusing to load it would brick the
  store over documents, and a store whose schema does not load has *no* working command except
  `version` (measured: `get`, `query`, `check`, `reindex` and `schema validate` all exit 3).
- **`check --fix` filling the field in.** There is no value to fill in — an owner or a tag is a
  decision, and guessing one is the same error as stamping `verified` on an unread document.
- **Relaxing the write.** Failing the write is correct; it is the *only* signal that is wrong.

## Actors affected

- ACT-002 repository maintainer / developer

## Evidence

- `src/docir/modules/documents/domain/services/graph_checks.py:92` — `check` never reads `required_fields`
- `src/docir/modules/documents/domain/services/graph_checks.py:169,268` — the two sibling findings
- `src/docir/modules/documents/domain/services/validation.py:35` — `validate_required_fields`
- `src/docir/modules/documents/application/services/document_service.py:158,206` — its only two callers
- `src/docir/modules/documents/infra/profiles.py` — why the change can arrive without a local edit

## Resolution

FIXED 2026-08-07, as proposed. `GraphChecker._find_missing_required` reports a
`missing-required` warning naming every field a document lacks that its type declares as
`required`, wired into `check` beside `unknown-status`.

Four scoping decisions, all as proposed:

- **Type-declared fields only.** `CORE_REQUIRED_FIELDS` are what makes a document parse, so an
  absent one is already `malformed`; reporting it twice only makes the healthy case noisier.
- **Warning severity.** `--strict` stays green. The rule change ships in the package, so an error
  kind would red-build every repo on the release that added the field — how the gate became
  unusable the first time.
- **One finding per document**, naming every missing field, so a schema requiring three of them
  does not triple the output on a corpus that predates them.
- **Unknown-type documents are skipped**, matching `unknown-status`: there is no type schema to
  read a `required` list from, and the cause is already reported once.

Archived documents are *not* skipped (unlike `unmatched-code`): the finding reports a rule the
document does not satisfy, and unarchiving is a write like any other.

The emptiness rule is now **shared** rather than restated — `validation._is_absent` became
`validation.is_absent` and both tiers call it. Two definitions of "empty" would eventually
disagree, and the disagreement is the worst one available: `check` calling a document conforming
that the next write refuses, or the reverse. `TestASchemaChangeThatMakesAFieldRequired` pins that
directly — it asserts the reported set against a write that really is refused.

Verified by injecting four bugs, each caught by a different test: unwiring the check, narrowing
the emptiness rule to `None`/`""`, promoting the kind to `ERROR_KINDS`, and dropping the
unknown-type guard.

Recovery is what the message names: `docir update <id> --set-owner ...` (or drop the requirement
from the schema). `check --fix` still does not touch it — an owner or a tag is a decision, and
there is no value to fill in.

Not addressed here, and left to the two sibling issues: nothing still reports that the *schema*
changed (issue-d891ab5501e6), so this finding is the symptom surfacing, not the cause.
