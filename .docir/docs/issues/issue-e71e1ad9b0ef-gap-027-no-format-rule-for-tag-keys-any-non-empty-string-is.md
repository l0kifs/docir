---
created: '2026-07-30'
description: Two agents will produce `auth`, `Auth` and `authentication` and nothing
  objects.
id: issue-e71e1ad9b0ef
owner: maintainer
related:
- adr-289e788719a7
status: resolved
tags:
- tags
- cosmetic
title: GAP-027 — No format rule for tag keys — any non-empty string is accepted
type: issue
updated: '2026-07-30'
---

# GAP-027 — No format rule for tag keys — any non-empty string is accepted

**Class:** missing · **Severity:** cosmetic · **Confidence:** observed
**Flow:** FLOW-005 · **Step:** tag add
**Question:** None · **Frequency:** unknown

## Finding

No format rule for tag keys — any non-empty string is accepted.

## What happens today

No charset, length, case or reserved-word check anywhere. Document ids are strictly regex-validated by contrast.

## Impact

Two agents will produce `auth`, `Auth` and `authentication` and nothing objects.

## Proposed default

Validate against `^[a-z][a-z0-9-]*$` and normalise case.

## Actors affected

- AI coding agent
- repository maintainer

## Evidence

- `src/docir/modules/tags/application/services/tag_service.py:43-52`
- `src/docir/modules/documents/domain/value_objects/identifiers.py:21`

---

Migrated from the discovery gap register (GAP-027); the register itself now lives in this store.

## Resolution

FIXED 2026-07-30. Tag keys must match `^[a-z][a-z0-9-]*$` (lowercase letters, digits and hyphens, starting with a letter). `tag add` and `tag rename` reject anything else with a Tier 0 `ValidationError`; `rename` validates only the NEW key, because renaming away from a legacy key is the migration path. Keys already in a registry are never rewritten — normalising case silently would rewrite the user's data — and are reported by `docir check` as a `tag-key-format` **warning**, so an existing corpus does not start failing `--strict` for something its author could not have avoided. `check --fix` deliberately does not repair it: only a human knows whether `Auth` meant `auth` or `authn`. The grammar lives in the new pure `platform.naming` leaf rather than being written twice, because `tags` applies it on write and `documents` applies it in the check and neither may import the other (ADR-0012, adr-289e788719a7). Verified by injecting both bugs: with the rejection and the check removed, 8 of the 12 new guards fail.
