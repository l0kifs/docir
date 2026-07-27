# FLOW-004 — Adopt docir in a repository (bootstrap, schema, agent onboarding)

## Backbone

install → `docir init` → choose profiles → `docir agent install` → first `add` → commit → teammate clones

## Event timeline

| # | Event | Actor | Trigger | Evidence |
|---|-------|-------|---------|----------|
| 1 | StoreInitialized | ACT-002 | `docir init [--profiles a,b] [--id-style s]` | composition.py:167-215 |
| 2 | SchemaWritten | system | `docs-schema.yaml` from core+profiles+id_style | composition.py:196-201 |
| 3 | IndexGitignored | system | `.docir/.gitignore` | composition.py:146-154 |
| 4 | MigrationsRun | system | same startup path as every command | composition.py:194 |
| 5 | AgentInstructionsInstalled | ACT-002 | `docir agent install [--agent …]` | agents/application/service.py:66-70 |
| 6 | StoreDiscovered | system | walk up from CWD for `.docir` | settings.py:35-48 |
| 7 | SchemaInspected | ACT-001/002 | `docir schema show` / `validate` | cli/app.py:124-146 |
| 8 | TeammateCloned | ACT-002 | `git clone`; index absent (gitignored) | README.md:143-148 |
| 9 | IndexRebuilt | ACT-002 | `docir reindex` | → FLOW-003 |

## Hotspots

- **H1 — step 8→9 is the entry point to `GAP-003`.** The clone story is the *reason* the index
  is gitignored, and it is the exact path that corrupts id allocation. Everything in this flow
  is correct right up to the point where a second person joins.

- **H2 — no `docir init` is required.** Every command silently falls back to a global
  `~/.docir` (settings.py:104) and `load_schema` writes a default schema on first touch
  (schema_loader.py:26-31, 35). Running `docir add` in an uninitialised repo therefore
  succeeds and writes the document into the user's *home* store, not the repo. Nothing warns.
  A user who forgets `init` gets a working command and silently misplaced documents.
  → `GAP-023`.

- **H3 — `docir agent install --agent <typo>` is a silent no-op.** Unknown target names are
  skipped without error (agents/application/service.py:96-98). CONFIRMED: `--agent claud`
  returned `[]`, exit code 0, wrote nothing. For a once-per-repo onboarding command, the user
  reasonably concludes their agent is configured when it is not. → `GAP-024`.

- **H4 — `docir schema validate` validates far less than its name claims.** CONFIRMED: a
  schema whose only transition target is a typo (`open: [closd]`) and whose
  `inactive_statuses` names an undeclared status (`done`) reports `{"valid":true}`. The defect
  surfaces later as `invalid transition 'open' -> 'closed'`, which points at the *write*, not
  at the schema — and `closed` genuinely is a declared status, so the message actively
  misdirects. Neither transition targets nor `inactive_statuses` are checked for membership in
  the declared status set, so a type can be authored with **no reachable exit from its default
  status**. → `GAP-010`.

- **H5 — disabling a profile strands existing documents.** Documented and deliberate
  (`unknown-type` finding, CLAUDE.md), and there is no migration path: the docs of the
  disabled type can no longer be validated, are never stale, and are skipped by layering
  checks. Behaviour is defined; the *recovery* is not. → `GAP-025`.

- **H6 — `.docir/.gitignore` is written only if absent**, and `docir init --force` overwrites
  both it and `docs-schema.yaml` together with no separate control and no diff/confirmation
  (composition.py:184-192). `--force` on a store with a customised schema destroys it. Nothing
  warns, nothing backs up. → `GAP-026`.

- **H7 — the id style is chosen once, at init, and cannot be changed afterwards.** `docir
  init` defaults to `id_style: random` (BR-074) precisely because a repo store is shared. But
  switching an existing store's style leaves the old documents in the old style, and there is
  no re-key operation — the same missing capability as `GAP-036`. Also `GAP-041`: the counter
  restore misreads an all-digit random id as sequential.

- **H8 — no import path for an existing corpus.** A repo that already keeps ADRs must
  re-create each one through `docir add`, and ids are always system-allocated, so historical
  ADR numbers cannot be preserved. → `GAP-036`.

## Off-system steps

- Committing `.docir/docs/` and `docs-schema.yaml`; deciding what the team's profiles are.
- Teaching a *non*-Claude, non-`AGENTS.md` agent to use docir (only two targets ship).

## Rules

BR-059, BR-060, BR-061, BR-062, BR-063, BR-064

## Gaps

GAP-010, GAP-023, GAP-024, GAP-025, GAP-026, GAP-036, GAP-041
