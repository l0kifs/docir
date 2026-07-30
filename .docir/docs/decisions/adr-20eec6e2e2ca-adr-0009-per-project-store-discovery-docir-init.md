---
created: '2026-07-24'
description: Why a project-local .docir store is discovered the way git finds .git.
id: adr-20eec6e2e2ca
owner: maintainer
related:
- kind: refines
  to: arch-1cfb1b212237
status: accepted
tags:
- cli
- persistence
title: 'ADR-0009: Per-project store discovery + docir init'
type: decision
updated: '2026-07-30'
---

# ADR-0009: Per-project store discovery + `docir init`

Status: accepted
Date: 2026-07-24

## Context
docir resolved its store from `DOCIR_HOME` or a single global `~/.docir` default
(ADR context in `config/settings.py`). That is a fine model for personal,
cross-project notes, but it has no per-repo story: running docir inside a project
wrote that project's docs into the global store, and the agent guide's own
"commit the docs" instruction was misleading because nothing landed in the repo.
For the common ask — "restructure this repo's existing docs into docir" — an
agent (or human) had no way to keep the docs *with the code* short of exporting
`DOCIR_HOME` in every shell.

## Decision
Add a **project-local store** discovered the way git finds `.git`, plus a
command to create one:

- **Discovery** (`config/settings.discover_project_home`): when neither an
  explicit `--home` nor `DOCIR_HOME` is set, `Settings.resolve` walks up from the
  working directory for a `.docir/` directory and uses the first one found;
  otherwise it falls back to the global `~/.docir`. New home precedence, highest
  first: `--home` → `DOCIR_HOME` → discovered project `.docir` → `~/.docir`.
- **`docir init [DIR] [--profiles ...] [--force]`**: creates `DIR/.docir`, writes
  a `docs-schema.yaml` (the bundled default, or with the chosen profiles), writes
  a `.gitignore` for the derived index + daemon runtime, ensures the directory
  layout, and runs migrations — the *same* startup path every command uses, so an
  initialized store is immediately valid. Existing files are preserved unless
  `--force`; an unknown profile is a `SchemaError` (exit 3).

Placement: the initialization logic is a **bootstrap** operation and lives in the
composition root (`entry_points/composition.initialize_store`), the one place
already allowed to touch every layer; the CLI command is a thin wrapper that runs
it in-process (no daemon/dispatcher, like `agent` and `version`). It reuses the
documents module's `DEFAULT_SCHEMA_YAML` / `PROFILE_NAMES` (newly exported from
`documents.api`, with the paired `CONTRACT.md` update) rather than reaching into
`documents.infra`.

## Consequences
- Easier: `docir init` scopes a repo's docs to the repo; commands run anywhere in
  the tree find the store automatically. The commit story is now honest —
  `.docir/docs/` + `docs-schema.yaml` are committed, the index is gitignored.
  This is what makes agent-driven doc migration land in the right place.
- Backward compatible: with no project `.docir` and no `DOCIR_HOME`, resolution
  still yields `~/.docir` exactly as before; every existing test sets
  `DOCIR_HOME`, so discovery never fires in the suite.
- Cost: `Settings.resolve` now reads the CWD (a `Path.cwd()` walk) when nothing
  else pins the home. This is pinned behind the "no explicit home / no env"
  branch, so it is inert whenever a home is given.
- Note: the global `~/.docir` remains a valid store and is itself just a `.docir`
  directory, so discovery and the default coincide when a repo sits directly
  under `~` with no store of its own — the same resolved path either way.
- Scoped out: no migration of an *existing* global store into a project store,
  and no multi-store federation/search across stores — one resolved store per
  invocation, as before.
