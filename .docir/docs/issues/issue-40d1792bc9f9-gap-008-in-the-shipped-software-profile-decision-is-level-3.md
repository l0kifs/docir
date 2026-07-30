---
created: '2026-07-30'
description: The most natural thing a user will model produces a warning they cannot
  silence, which trains them to ignore `check` output — and compounds GAP-006.
id: issue-40d1792bc9f9
owner: maintainer
related:
- adr-2a3f625bb2f8
- arch-0a3c2d6d54a6
- ref-1509d5dbb4c3
status: resolved
tags:
- integrity
- material
title: GAP-008 — In the shipped `software` profile, `decision` is level 3 and `issue`
  is level 1, so…
type: issue
updated: '2026-07-30'
---

# GAP-008 — In the shipped `software` profile, `decision` is level 3 and `issue` is level 1, so…

**Class:** incorrect · **Severity:** material · **Confidence:** observed
**Flow:** FLOW-003 · **Step:** layering check under the default profile
**Question:** Q-006 · **Frequency:** any corpus where a decision links its motivating issue

## Finding

In the shipped `software` profile, `decision` is level 3 and `issue` is level 1, so linking a decision to the issue that motivated it is a permanent layering violation.

## What happens today

OBSERVED. `adr-0001 related: [issue-0003]` yields "layering violation: decision 'adr-0001' depends on lower-level issue 'issue-0003'". This is the exact pairing in the README's own quickstart output (README:78-81).

## Impact

The most natural thing a user will model produces a warning they cannot silence, which trains them to ignore `check` output — and compounds GAP-006.

## Proposed default

Restrict the layering check to `depends_on` (and `refines`) rather than "everything except supersedes/contradicts". `relates_to` is the default kind applied to every bare id and carries no dependency claim at all.

## Resolution

FIXED 2026-07-27, as proposed, under Q-006's recorded assumption (the maintainer directed the work without answering the question separately). `_NON_DEPENDENCY_KINDS` is inverted into `_DEPENDENCY_KINDS = {depends_on, refines}`: a layering violation is now read only from an edge that actually asserts a dependency. `relates_to`, `supersedes`, `contradicts` and `implements` no longer produce one. Verified against the real CLI, replaying PROBE-8: `adr-0001 related: [issue-0001]` — the README quickstart pairing — now reports `[]` where it reported a permanent violation, and the same edge retyped `issue-0001:depends_on` still flags (severity `warning`, `--strict` exit 0). `implements` is excluded on purpose: it points implementation -> spec by its nature, so its direction carries no claim about which document may rely on which. Accepted consequence: a relation kind added by a custom schema is not layering-checked until it is named in `_DEPENDENCY_KINDS`. Silence on an unknown kind is the right default for a heuristic warning; noise on a correct one is not — that was the whole defect. NOTE, the same trap as GAP-006: `test_layering_violation` asserted the old behaviour as intent (it built a default-kind edge and required a violation), so the test suite could never have caught this. It now uses `depends_on`, and `test_relates_to_never_reports_layering` pins the actual rule.

## Actors affected

- repository maintainer
- CI job

## Evidence

- `src/docir/modules/documents/infra/profiles.py:26-27, 44-46`
- `src/docir/modules/documents/domain/services/graph_checks.py:194-223`
- `ref-1509d5dbb4c3 (discovery probe log)`

---

Migrated from the discovery gap register (GAP-008); the register itself now lives in this store.
