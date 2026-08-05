---
created: '2026-07-26'
description: Why a qa profile, a release_note type and schema introspection were added.
id: adr-c0ce6f347f3e
owner: maintainer
related:
- kind: refines
  to: adr-2a3f625bb2f8
- adr-3a2d5ee7bc84
- adr-20eec6e2e2ca
status: accepted
tags:
- schema
- cli
title: A qa profile, a release_note type, and schema introspection
type: decision
updated: '2026-08-05'
---

## Context
Two gaps surfaced while evaluating docir against an external, documentation-mature
repository (a QA automation platform with ~85 governed markdown files: ADRs,
module contracts, business-flow acceptance specs, task specs, runbooks).

**1. An agent cannot author a schema.** The bundled agent skill (adr-3a2d5ee7bc84) told
agents to "add inline `types:`" but never showed the syntax. Three keys are
required by the loader — `prefix`, `statuses` (a *mapping*, not a list), and
`default_status` — and none were documented anywhere an agent could read: not in
the skill, not in the generated `docs-schema.yaml` comments. Nor was global
prefix uniqueness, the `allowed_relations` whitelist semantics, or the
`relation_types` registration syntax. There was also no way to *inspect* the
merged schema or check an edit: the only feedback was a `SchemaError` raised by
the next unrelated write. Schema editing is the one write with no CLI path, so
the failure mode was an agent silently guessing and getting a Tier 0 error.

**2. No testing vocabulary.** docir is aimed at engineering teams, yet no bundled
profile offered a type for a test plan or a test case — the most common
non-ADR document in a QA-owned repo. Release notes were likewise absent despite
being near-universal for software.

## Decision
**Add a `qa` profile** (`test_plan`, `test_case`) and **add `release_note` to the
`software` profile**. Adding types to a profile is backward compatible: existing
documents keep their type, and the new types are simply available. (Removing one
would not be — an existing doc would become `unknown-type` — which is why the
change is additive only.)

**Add `docir schema show` and `docir schema validate`.** Both run **in-process,
bypassing the daemon/dispatcher**, because `build_container` loads the schema:
routing them through the dispatcher would make the commands meant to diagnose a
broken schema unreachable precisely when the schema is broken. This follows the
`init` / `agent` / `version` precedent (adr-3a2d5ee7bc84, adr-20eec6e2e2ca) — they touch no
index/DB state, so the entry point builds what it needs directly. `show` reports
the *merged* schema (core + profiles + inline), which is what validation actually
enforces; the raw file only lists the ingredients.

**Document the grammar where it is used.** A worked, commented-out `types:` /
`relation_types:` example now ships inside the generated `docs-schema.yaml`
itself, so an agent editing that file learns the syntax from the file. The skill
gains a required/optional key table and an explicit warning about the
`allowed_relations` whitelist trap.

**Make the `--profiles` substitution structural.** `initialize_store` previously
built the schema body by string-replacing the literal `profiles: [software]` in
`DEFAULT_SCHEMA_YAML`. If that line ever changed, the replace would silently
no-op and `init` would write the default profiles while *reporting* the requested
ones. The body is now assembled by `render_schema_yaml(profiles)` from a header
and footer around a generated `profiles:` line — divergence is unrepresentable.
This was latent, not live; adding the commented example to that constant is
exactly the edit that would have triggered it.

### Considered and rejected
Three further types were proposed from the same source repo and deliberately
**not** bundled. The bar for a bundled type is "would several unrelated teams in
this domain use it?", not "did one repo need it" — generalizing from n=1 is how a
shipped schema rots. Each remains easy to add as an inline type.

- **`api_contract`** (a module's public surface). An artifact of one architecture
  style (a `CONTRACT.md` per module — docir's own house style, which is precisely
  the bias to be careful of). Also collides with `legal.contract` on the natural
  `ctr` prefix.
- **`task`** (a `todo/`→`done/` work item). `issue` already covers work items,
  and a task type invites scope creep toward being a tracker, which docir is not.
- **`requirement`**. Plausible in a future `product` profile alongside
  `feature`/`spec`, but the evidence is a single repository. Deferred until a
  second, independent data point.

The default profile selection stays `[software]`. It only affects new `init`s
(an existing `docs-schema.yaml` is never overwritten), so widening it is low
value — and every unused type is noise in the agent's per-document type choice.

## Consequences
- Easier: QA-owned repos have native types; an agent can read the active schema
  (`schema show`) and check an edit (`schema validate`) instead of guessing; the
  syntax is discoverable from the schema file itself.
- Harder: five bundled profiles now share one global prefix namespace, so each
  new bundled type must be checked against every other profile's prefixes. The
  `tp`/`tc`/`rel` prefixes are reserved.
- `DEFAULT_SCHEMA_YAML` is now derived from `render_schema_yaml()` rather than
  being a hand-written literal; both are exported from `documents.api`.
- Follow-up: `schema show` is read-only. If schema editing ever warrants a real
  write path (`docir schema add-type`), it would supersede the "hand-edit the
  YAML" guidance in the skill.
