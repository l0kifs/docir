---
created: '2026-07-30'
description: Documents intended for a repo land in the user's home directory, ungitted
  and invisible to teammates, with no error at any point.
id: issue-34b4f0ca1e13
owner: maintainer
related:
- adr-20eec6e2e2ca
- arch-90c90751344f
- issue-40d1792bc9f9
- issue-9cb85759076d
status: resolved
tags:
- cli
- material
title: An uninitialised repository silently falls back to the global `~/.docir` store
type: issue
updated: '2026-08-05'
---

**Class:** misleading · **Severity:** material
**Flow:** arch-90c90751344f · **Step:** running a command before docir init
**Question:** issue-b86a75d656ea · **Frequency:** any user who forgets `docir init` — the second step of the quickstart

## Finding

Commands run in an uninitialised repository silently fall back to the global `~/.docir` and succeed, writing documents outside the repo.

## What happens today

`Settings.resolve` returns the global default with no signal (settings.py:104), and `load_schema` writes a default schema on first touch (schema_loader.py:26-31). `docir add` reports success and a relative path that looks repo-local.

## Impact

Documents intended for a repo land in the user's home directory, ungitted and invisible to teammates, with no error at any point.

## Proposed default

Report the resolved store (and whether it was discovered or defaulted) in write-command output, or warn once when falling back to global.

## Resolution

FIXED 2026-07-29, taking both halves of the proposed default rather than choosing between them, because they address different things. (1) Every write reports the resolved `store`. This is the part that fixes "misleading": `path` is relative to the *store*, so it read as repo-local wherever the store actually was, and nothing in the payload named it. Zero noise, machine-readable, and it removes the ambiguity for every write whether or not anything warns. (2) A stderr warning, but ONLY when the global fallback happens inside a git repository. `Settings` now records `home_origin` (flag | env | project | global) and `is_unintended_global_fallback()` combines it with an upward walk for `.git` — the same walk `discover_project_home` does, one directory name over. THE NARROWING IS THE DESIGN, NOT AN OPTIMISATION. The global store is a real feature for personal notes, so falling back to it is not an error and erroring would break that workflow. Warning on *every* fallback would fire on correct usage — the issue-9cb85759076d/issue-40d1792bc9f9 failure mode, hit three times in this codebase already. Inside a repo with no `.docir/` is the one case where the user almost certainly meant the repo. NO NEW FLAG for the opt-out: setting `DOCIR_HOME` takes the `env` branch rather than the fallback branch, so someone who does mean the global store from inside a repo already has a way to say so. Pinned by test_explicit_docir_home_opts_out. Verified on the real CLI across all three shapes: repo without `.docir` warns, plain directory does not, repo with `.docir` does not — and `store` is present in all three.

## Actors affected

- repository maintainer
- AI coding agent

## Evidence

- `src/docir/config/settings.py:96-104`
- `src/docir/modules/documents/infra/schema_loader.py:26-31`

---

Migrated from the discovery gap register (GAP-023); the register itself now lives in this store.
