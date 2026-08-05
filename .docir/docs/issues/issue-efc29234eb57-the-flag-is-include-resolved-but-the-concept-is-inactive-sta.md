---
created: '2026-07-30'
description: A user querying decisions has no reason to guess that a flag named --include-resolved
  controls whether superseded decisions appear.
id: issue-efc29234eb57
owner: maintainer
related:
- adr-2a3f625bb2f8
- arch-f220a644d654
- issue-8c37bf22ba3c
- issue-be95d3e242a3
status: resolved
tags:
- schema
- material
title: The flag is `--include-resolved` but the concept is "inactive status"
type: issue
updated: '2026-08-05'
---

**Class:** misleading · **Severity:** material
**Flow:** arch-f220a644d654 · **Step:** asking for closed documents
**Question:** None · **Frequency:** any query for closed documents of a type without a `resolved` status

## Finding

The flag is `--include-resolved` but the concept is "inactive status", which is `rejected`/`superseded` for decisions, `deprecated` for architecture, `retired` for policy, and so on. `resolved` is a status of only two of the fifteen shipped types.

## What happens today

The wire field is named `include_inactive` (dispatch.py:116) and the CLI renames it to `--include-resolved` on the way out (app.py:269, 288, 303).

## Impact

A user querying decisions has no reason to guess that a flag named --include-resolved controls whether superseded decisions appear.

## Proposed default

Rename to `--include-inactive` (keeping `--include-resolved` as a hidden alias), matching the internal name and the schema key.

## Resolution

FIXED 2026-07-28, as proposed, on all three read commands (query/search/context). `--include-inactive` is the documented flag; `--include-resolved` remains accepted but hidden, because it appears in scripts and in agent instruction files installed before this release — breaking it would be a silent behaviour change for them. Using it prints a deprecation notice to **stderr**, never stdout, so a captured JSON payload is untouched. FOUND WHILE DOING IT — `describe_help` filtered hidden *commands* but not hidden *options*. The asymmetry was invisible while nothing was hidden; the first deprecated alias then disappeared from the Rich panel a human reads and stayed in the JSON help an agent reads. That is precisely backwards: the JSON help is the agent contract, and two flags for one concept there is the confusion this gap is about. Both are now filtered, pinned by test_hidden_options_stay_out_of_the_agent_contract (verified to fail against the old comprehension). The general shape, third time recorded: a rule applied to one of two parallel paths. issue-8c37bf22ba3c was the visibility filter on 3 of 4 read paths; issue-be95d3e242a3 is the stale-write guard on 1 of 5 edit modes and is still open. Worth grepping for the rest.

## Actors affected

- AI coding agent
- repository maintainer

## Evidence

- `src/docir/entry_points/cli/app.py:269`
- `src/docir/entry_points/dispatch.py:116`
- `src/docir/modules/documents/infra/profiles.py`

---

Migrated from the discovery gap register (GAP-033); the register itself now lives in this store.
