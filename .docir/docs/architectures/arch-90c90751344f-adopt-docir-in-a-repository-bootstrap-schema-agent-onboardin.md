---
code:
- src/docir/entry_points/composition.py
- src/docir/config/settings.py
- src/docir/modules/documents/infra/schema_loader.py
- src/docir/modules/agents/**
code_baseline:
  src/docir/config/settings.py: 49d614f03082
  src/docir/entry_points/composition.py: f1e7c5f79526
  src/docir/modules/agents/**: fba99326556f
  src/docir/modules/documents/infra/schema_loader.py: 4cbd9ed6460b
created: '2026-07-30'
description: How a repository gets a store and an agent learns to drive it.
id: arch-90c90751344f
owner: maintainer
related:
- arch-0a3c2d6d54a6
- arch-1cfb1b212237
- issue-20933967697b
- issue-34b4f0ca1e13
- issue-b47a1203baa2
- issue-b7ddde3ce860
- issue-b8220546282c
- issue-ed49c1d03894
- issue-f09fab3f5c36
- issue-fde9a7151bd1
status: active
tags:
- agents
- cli
title: Adopt docir in a repository (bootstrap, schema, agent onboarding)
type: architecture
updated: '2026-09-17'
---

## Backbone

install → `docir init` → choose profiles → `docir agent install` → first `add` → commit → teammate clones

## Event timeline

| # | Event | Actor | Trigger | Evidence |
|---|-------|-------|---------|----------|
| 1 | StoreInitialized | ACT-002 | `docir init [--profiles a,b] [--id-style s]` | composition.py:534 |
| 2 | SchemaWritten | system | `docs-schema.yaml` from core+profiles+id_style | composition.py:573-577 |
| 3 | IndexGitignored | system | `.docir/.gitignore` | composition.py:470 |
| 4 | MigrationsRun | system | same startup path as every command | composition.py:586 |
| 5 | AgentInstructionsInstalled | ACT-002 | `docir agent install [--agent …]` | agents/application/service.py:75 |
| 6 | StoreDiscovered | system | walk up from CWD for `.docir` | settings.py:48 |
| 7 | SchemaInspected | ACT-001/002 | `docir schema show` / `validate` | cli/schema_cmds.py:17-30 |
| 8 | TeammateCloned | ACT-002 | `git clone`; index absent (gitignored) | README.md |
| 9 | IndexRebuilt | ACT-002 | `docir reindex` | → arch-0a3c2d6d54a6 |

## Hotspots

Eight hotspots were confirmed by the 2026-07-26 discovery pass. **All eight are closed.**
They are kept as the record of what adoption looked like before the fixes — read each one's
*Closed* line for the behaviour that ships today, and the linked issue for the argument.

### H1 — a fresh clone's first `add` re-minted a live id

Step 8→9 was the entry point to `issue-b7ddde3ce860`: the clone story is the *reason* the
index is gitignored, and rebuilding it lost the id counter.

*Closed* — `reindex` restores the counter from the files (`index_rebuilder.py`,
`_restore_id_sequences`), and a create refuses to write onto an id a file already claims.
Opening a store whose index is empty now rebuilds it before anything is dispatched
(adr-e53c813d2f13), so the clone path runs the restore on its own. → arch-0a3c2d6d54a6.

### H2 — no `docir init` was required, and nothing warned

Every command fell back to the global `~/.docir` silently, so `docir add` in an uninitialised
repository succeeded and wrote the document into the user's *home* store.

*Closed* — the fallback still exists (`settings.py:161`), but from inside a repository docir
now warns on stderr that the store is the global one (`Settings.is_unintended_global_fallback`,
`emit.warn_on_global_fallback`), and every write reports its `store`. → `issue-34b4f0ca1e13`.

### H3 — `docir agent install --agent <typo>` was a silent no-op

Unknown target names were skipped without error: `--agent claud` returned `[]`, exit 0, wrote
nothing, and the user reasonably concluded their agent was configured.

*Closed* — an unknown name is refused with an `AgentSetupError` that lists the valid targets
(`agents/application/service.py`). → `issue-b8220546282c`.

### H4 — `docir schema validate` validated far less than its name claimed

A transition target that was a typo (`open: [closd]`) and an `inactive_statuses` entry naming
an undeclared status both reported `{"valid": true}`, and the defect surfaced later as a
misdirecting write error.

*Closed* — the loader refuses both at load time (`schema_loader.py`: a transition to an
undeclared status and an `inactive_statuses` entry naming one are each a `SchemaError`), so
`schema validate` reports them before any write; it also measures the documents on disk
against the file (adr-dbe6633405ca). → `issue-b47a1203baa2`.

### H5 — disabling a profile stranded existing documents

The behaviour was defined (`unknown-type`), the *recovery* was not.

*Closed* — the packaged skill documents it (`reference/maintenance.md`, "Recovering from
`unknown-type`", and `reference/schema.md`), and `docir update <id> --type` retypes a document
out of a type the schema no longer declares (adr-f8cce745d0d5). → `issue-ed49c1d03894`.

### H6 — `init --force` overwrote a customised schema along with the `.gitignore`

One flag, two files, no separate control.

*Closed* — `--force` regenerates the `.gitignore` always and the schema only while it is
unmodified; a customised `docs-schema.yaml` is kept and reported as `schema_preserved`, and
replacing it takes `--force-schema` (`composition.py`, `_schema_write_plan`).
→ `issue-fde9a7151bd1`.

### H7 — the id style is chosen once, at init

`docir init` defaults to `id_style: random` because a repo store is shared; switching an
existing store's style leaves the old documents in the old style, and there is still no
re-key operation — deliberately.

*Closed for the defect it carried* — the counter restore no longer misreads an all-digit
random suffix as a sequential number (`index_rebuilder.py`, `looks_random`).
→ `issue-f09fab3f5c36`.

### H8 — no import path for an existing corpus

A repository that already keeps ADRs re-creates each one through `docir add`.

*Closed* — there is deliberately no bulk import, but `docir add --id adr-0007` preserves a
historical number on a sequential-style store, which is what the re-creation needed.
→ `issue-20933967697b`.

## Off-system steps

- Committing `.docir/docs/` and `docs-schema.yaml`; deciding what the team's profiles are.
- Teaching an agent that neither loads Claude skills, reads `AGENTS.md`, nor speaks MCP (four
  `--agent` targets and `docir mcp serve` ship).

## Rules

BR-059, BR-060, BR-061, BR-062, BR-063, BR-064

## Gaps

All seven filed by the discovery pass are resolved: issue-b47a1203baa2, issue-34b4f0ca1e13,
issue-b8220546282c, issue-ed49c1d03894, issue-fde9a7151bd1, issue-20933967697b,
issue-f09fab3f5c36. Nothing here is open.
