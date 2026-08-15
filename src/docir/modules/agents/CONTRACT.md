# agents

## Purpose
Installs and refreshes the AI-assistant instruction files for docir — two Claude
Code skills and an `AGENTS.md` block that **links** to them. `claude`
(`.claude/skills/docir/SKILL.md`) teaches the CLI; `claude-writing`
(`.claude/skills/docir-writing/SKILL.md`) teaches how to write the documents and
is opt-in (adr-735ba7f6209b). Each installs one packaged template verbatim, and
the block carries only those templates' `description` plus the path to each file
(adr-6ed847e02fe5).

## Public operations
- `build_agent_service(version) -> AgentSetupService` — wire the service (the
  running docir `version` is stamped into every generated file)
- `AgentSetupService.install(InstallRequest) -> SetupResult` — write the
  requested targets (default: the Claude skill)
- `AgentSetupService.update(UpdateRequest) -> SetupResult` — refresh
  already-installed targets to the current version; `agents` names targets to add

`InstallRequest`/`UpdateRequest` carry `project_root`, `global_root`, an `agents`
tuple of target names (`AGENT_NAMES`), and `use_global`. `SetupResult.files` is a
tuple of `InstalledFile{target, path, action, previous_version, new_version,
note}` where `action` is an `InstallAction` (`created`/`updated`/`skipped`). A
`--global` install of a target with no global location (e.g. `agents`) raises
`AgentSetupError`.

## Behavioural guarantees
- A skill file is entirely docir's and is rewritten wholesale.
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
- A block written before the pointer form is replaced by one on the next
  `update`, reported as a note on that file.
- Generated files carry a parseable version stamp so `update` reports the
  installed→refreshed transition.

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
