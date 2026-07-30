---
created: '2026-07-22'
description: Why tests live in a central tree mirroring the modules instead of beside
  them.
id: adr-909fc2a170d0
owner: maintainer
related:
- kind: contradicts
  to: arch-322e5f992ad2
status: accepted
tags:
- testing
- architecture
title: 'ADR-0004: Keep a central test tree, organized per module'
type: decision
updated: '2026-07-30'
---

# ADR-0004: Keep a central test tree, organized per module
Status: accepted
Date: 2026-07-22

## Context
ARCHITECTURE_RULES §9 asks for tests to live inside the module they cover,
mirroring its structure, so the module layout also removes test fan-out. The
existing suite is a single top-level `tests/` tree that is green (176 tests).
Relocating every test into `src/docir/modules/**` in the same change as the
structural refactor multiplies the churn and the chance of breakage.

## Decision
Keep the central `tests/` tree for now, but organize it to mirror the module
structure — `tests/modules/{documents,tags,indexing}/`, `tests/platform/`,
`tests/entry_points/` — so each test's owning context is unambiguous. Defer
co-locating tests inside `src/docir/modules/**` to a later, isolated change.

## Consequences
- Easier: the refactor lands without touching test bodies; ownership is still
  legible from the directory a test lives in.
- Harder: tests are not yet physically inside their module, so a module is not
  fully self-contained per §9.
- This is a recorded deviation from §9 (a SHOULD/MUST on test location); moving
  the tests into the modules is the sanctioned follow-up that supersedes it.
