---
created: '2026-07-30'
description: A store is created somewhere the user did not ask for, and if the CWD
  happens to be a repository they now have an unrequested `.docir/` in it — which
  is exactly what happened to the analyst while…
id: issue-638068ed09a6
owner: maintainer
related:
- adr-20eec6e2e2ca
- arch-90c90751344f
- ref-1509d5dbb4c3
status: resolved
tags:
- cli
- material
title: GAP-047 — `docir init` ignores the global `--home` flag. The store is created
  under the CWD…
type: issue
updated: '2026-07-30'
---

# GAP-047 — `docir init` ignores the global `--home` flag. The store is created under the CWD…

**Class:** incorrect · **Severity:** material · **Confidence:** observed
**Flow:** FLOW-004 · **Step:** docir --home <path> init
**Question:** None · **Frequency:** any `--home` used with `init`

## Finding

`docir init` ignores the global `--home` flag. The store is created under the CWD regardless, and the reported `home` is the CWD path, so the output describes what happened but the flag was silently discarded.

## What happens today

OBSERVED. From an unrelated directory, `docir --home /tmp/x/target init` created `<cwd>/.docir` and reported that path as `home`; `/tmp/x/target` was not created. Every other command honours `--home`. `init` computes its own home from the `directory` argument (`app.py`: `directory.resolve() / PROJECT_STORE_DIRNAME`) and never consults the resolved settings.

## Impact

A store is created somewhere the user did not ask for, and if the CWD happens to be a repository they now have an unrequested `.docir/` in it — which is exactly what happened to the analyst while probing. The one flag whose entire purpose is "put the store here" is the one flag this command ignores. Predates the original run; missed by it.

## Proposed default

Either honour `--home` (it is more specific than the positional directory, so it should win), or reject the combination naming the positional argument as the way to choose a location. Silently discarding it is the only option that should not stand.

## Resolution

FIXED 2026-07-29. `--home` now names the store directly, as it does for every other command; the positional directory still means "the project whose .docir is the store"; and passing both is a ValidationError naming what each would do. Silently preferring one was the defect, so the conflict is refused rather than resolved by precedence. The error goes through `run_local`, because the first version raised outside it and surfaced as a traceback — the same escape the schema loader had (fixed while writing the hand-editing contract). Any new pre-dispatch validation has to be wrapped; that is now twice. ROOT CAUSE, and addressed rather than just noted: `init` was the only command that built its own home instead of consuming the resolved `Settings`, so a review tracing `Settings.resolve` never saw it — which is how the original pass missed it. "Every command honours --home" was a claim about a resolver, and the exception was the one command that does not use it. The rule now lives in `config/settings.py` as `new_store_home`, directly beside `resolve`, with each docstring naming the other: the two home decisions in this codebase are read together or not at all. The CLI keeps only the flag plumbing and the `ValueError -> ValidationError` translation, because `config` is a dependency leaf (`depends_on = []`) and cannot import the error taxonomy. `new_store_home` deliberately does *not* walk up for an existing `.docir` the way `resolve` does — reusing a parent store is the wrong answer when the caller is asking to create one. Pinned by its own unit test.

## Actors affected

- repository maintainer
- AI coding agent

## Evidence

- `src/docir/entry_points/cli/app.py`
- `ref-1509d5dbb4c3 (discovery probe log)`

---

Migrated from the discovery gap register (GAP-047); the register itself now lives in this store.
