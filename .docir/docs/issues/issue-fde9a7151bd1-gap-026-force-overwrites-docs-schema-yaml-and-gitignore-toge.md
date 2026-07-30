---
created: '2026-07-30'
description: A user re-running init to refresh the .gitignore destroys a customised
  schema.
id: issue-fde9a7151bd1
owner: maintainer
related:
- adr-20eec6e2e2ca
- arch-90c90751344f
status: resolved
tags:
- cli
- material
title: GAP-026 — `--force` overwrites `docs-schema.yaml` and `.gitignore` together,
  with no separate…
type: issue
updated: '2026-07-30'
---

# GAP-026 — `--force` overwrites `docs-schema.yaml` and `.gitignore` together, with no separate…

**Class:** unstated · **Severity:** material · **Confidence:** observed
**Flow:** FLOW-004 · **Step:** docir init --force
**Question:** None · **Frequency:** unknown

## Finding

`--force` overwrites `docs-schema.yaml` and `.gitignore` together, with no separate control, no confirmation prompt, no diff and no backup.

## What happens today

composition.py:184-192 — both writes are guarded by the same `force` flag. The help text reads 'Overwrite an existing docs-schema.yaml / .gitignore.'

## Impact

A user re-running init to refresh the .gitignore destroys a customised schema. The schema is the one file whose loss cannot be reconstructed from the documents.

## Proposed default

Separate the flags, or refuse when the existing schema differs from the generated one unless a second confirmation is given.

## Resolution

FIXED 2026-07-29, taking the second option but *skipping* rather than refusing. `--force` regenerates the `.gitignore` and a schema still byte-identical to what `init` would write; a schema that has been customised is kept, reported as `schema_preserved: true`, and named in a stderr warning that points at `--force-schema`. Verified end to end: with a customised schema and a stale `.gitignore`, `init --force` exits 0, refreshes the gitignore and leaves the custom type in place. THE FIRST ATTEMPT RAISED, AND WAS WRONG. `_may_write_schema` threw a `SchemaError` whose message said "the .gitignore is regenerated either way" — but the raise happened before the gitignore write, so the message was false and the user was left with neither. That is the worst outcome: refreshing the gitignore is the whole reason they ran the command, and the only way to get it became `--force-schema`, which destroys the schema. Caught by running the scenario from this gap's own impact statement instead of trusting the unit tests, which passed. The asymmetry is the point and is now stated in code: the `.gitignore` is a constant this module generates, so losing it costs nothing; the schema holds every type, status and cadence a person decided on and cannot be rebuilt from the documents. One flag for two files of such different value was the defect. SIXTH instance of the encoded-defect trap: the existing test was named `test_force_overwrites_schema`, wrote a customised schema, and asserted it was clobbered.

## Actors affected

- repository maintainer

## Evidence

- `src/docir/entry_points/composition.py:182-192`
- `src/docir/entry_points/cli/app.py:97-100`

---

Migrated from the discovery gap register (GAP-026); the register itself now lives in this store.
