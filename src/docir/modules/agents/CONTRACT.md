# agents

## Purpose
Installs and refreshes the AI-assistant instruction files for docir — three
Claude Code skills and an `AGENTS.md` block that **links** to them. `claude`
(`.claude/skills/docir/SKILL.md`) teaches the CLI; `claude-writing`
(`.claude/skills/docir-writing/SKILL.md`) teaches how to write the documents and
is opt-in (adr-735ba7f6209b); `claude-feedback`
(`.claude/skills/docir-feedback/SKILL.md`) teaches how to report a docir defect
upstream instead of working around it, and is opt-in for a stronger reason —
it ends in something leaving the machine (adr-7144cf291b1a). Each installs one
packaged template *directory* verbatim — an entry `SKILL.md` plus the reference
files it links — and the block carries only those templates' `description` plus
the path to each entry point (adr-6ed847e02fe5).

## Public operations
- `build_agent_service(version) -> AgentSetupService` — wire the service (the
  running docir `version` is stamped into every generated file)
- `AgentSetupService.install(InstallRequest) -> SetupResult` — write the
  requested targets (default: the Claude skill)
- `AgentSetupService.update(UpdateRequest) -> SetupResult` — refresh
  already-installed targets to the current version; `agents` names targets to add

`AGENT_NAMES` lists every selectable target and `FEEDBACK_AGENT` names the
opt-in upstream-feedback skill, so a caller that suggests it cannot print a name
the catalogue no longer has.

`InstallRequest`/`UpdateRequest` carry `project_root`, `global_root`, an `agents`
tuple of target names (`AGENT_NAMES`), and `use_global`. `SetupResult.files` is a
tuple of `InstalledFile{target, path, action, previous_version, new_version,
note, extras, removed}` — one row per *target*, where `path` is the entry point,
`extras` names the bundled files written beside it (`/`-separated, relative to
its directory) and `removed` names the files swept from a skill's directory.
`action` is an `InstallAction` (`created`/`updated`/`unchanged`/`skipped`). A
`--global` install of a target with no global location (e.g. `agents`) raises
`AgentSetupError`.

## Behavioural guarantees
- A skill *directory* is entirely docir's and is regenerated wholesale: every
  packaged file is written, and every `.md` under that directory which this build
  does not ship is deleted and named in `removed`. The sweep never leaves the
  skill's own directory, so a second skill and any foreign file elsewhere in the
  tree are untouched.
- A skill's `action` is aggregated over its whole directory: a release that only
  adds or drops a reference file is `updated`, even though the entry point
  differs by nothing but its stamp.
- An `AGENTS.md` is only touched inside docir's `<!-- docir:start/end -->` block
  (replaced, not duplicated); a foreign `AGENTS.md` is never rewritten by
  `update` unless `agents` is explicitly requested (then the block is appended).
- **Selecting a pointer target also writes the skills it names**, on both
  `install` and `update` — so the block never links a file that is not there,
  including after someone deletes the skill and keeps the block. The linked path
  is always `/`-separated.
- **The block indexes every skill installed under the same root**, not only the
  ones it names, and installing a skill refreshes an already-installed block in
  the same run. An optional skill therefore appears in the index once it exists
  without the index pulling it in for everyone.
- **No target is ever selected on the user's behalf.** `DEFAULT_AGENTS` holds
  `claude` only; `claude-writing` and `claude-feedback` are written solely when
  named by `--agent`. The module neither prompts nor persists a choice — the CLI
  layer *suggests* the optional skills in its human output, and an unattended
  install therefore writes exactly what it was asked for.
- A block written before the pointer form is replaced by one on the next
  `update`, reported as a note on that file.
- Generated files carry a parseable version stamp so `update` reports the
  installed→refreshed transition.
- A release that ships no change to a target's content is reported as
  `unchanged`, not `updated`: the file is still rewritten so its stamp names the
  running build, but a stamp that moved on its own is not a content change.

## Events published
- none (no event bus; see adr-d3e3616400bf)

## Events consumed
- none

## Owns
- data: none. This module holds no index/database state; it writes instruction
  files into the target tree (project root or `~/`) and reads its own packaged
  template. It does not participate in the shared unit-of-work.

## Depends on
- modules: none
- platform: errors

## Policy
- permissions: none (single-user local CLI; see adr-90e994d931cc)
- transport: runs in-process only; not routed through the daemon/dispatcher
  (see adr-3a2d5ee7bc84)
