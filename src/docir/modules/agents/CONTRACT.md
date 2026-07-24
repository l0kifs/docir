# agents

## Purpose
Installs and refreshes the AI-assistant instruction files that teach a coding
agent to drive docir — a Claude Code skill (`.claude/skills/docir/SKILL.md`) and
an `AGENTS.md` block. One packaged instruction template is the single source of
truth for what every target embeds.

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
- Generated files carry a parseable version stamp so `update` reports the
  installed→refreshed transition.

## Events published
- none (no event bus; see ADR-0002)

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
- permissions: none (single-user local CLI; see ADR-0003)
- transport: runs in-process only; not routed through the daemon/dispatcher
  (see ADR-0008)
