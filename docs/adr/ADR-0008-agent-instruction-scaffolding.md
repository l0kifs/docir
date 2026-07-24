# ADR-0008: Agent-instruction scaffolding as a self-contained module

Status: accepted
Date: 2026-07-24

## Context
docir is only useful to an AI coding agent if the agent knows it exists and how
to drive it (the read/write loop, the "never edit markdown by hand" rule). That
knowledge lived in a hand-written `docs/AGENT_GUIDE.md` that was **not packaged**
and had **no install path** — a user had to copy it into their assistant's
instruction file by hand. We want `docir` to install those instructions itself,
the way `uipilot init` does.

Two shapes an assistant reads instructions from cover the field: a **Claude Code
skill** (auto-loaded by its frontmatter `description`) and the cross-assistant
**`AGENTS.md`** convention. Everything else (Cursor, Copilot, Windsurf) either
reads `AGENTS.md` or is out of scope for now.

This operation is unlike every other docir command: it touches **no documents,
index, embeddings, or database** — it copies a packaged template into the target
tree. That raises two placement questions: which layer owns it, and whether it
goes through the daemon/dispatcher write path.

## Decision
Add a **self-contained bounded-context module `modules/agents`** (`api.py` +
`CONTRACT.md` + `domain`/`application`/`infra`), exposed as two CLI commands:

```
docir agent install [DIR] [--agent claude|agents ...] [--global]
docir agent update  [DIR] [--agent claude|agents ...] [--global]
```

- **Targets** (`domain/targets.py`): `claude` → `.claude/skills/docir/SKILL.md`
  (default; installable `--global` under `~/`) and `agents` → `AGENTS.md` at the
  repo root (project-only; no global location). Unknown `--agent` names are
  ignored; `--global` of a non-global target is an `AgentSetupError`.
- **Single source of truth**: one packaged template
  (`infra/templates/skill.md`) — the former `AGENT_GUIDE.md` plus skill
  frontmatter — is what the skill installs verbatim and what `AGENTS.md` embeds
  (frontmatter stripped) inside `<!-- docir:start/end -->` markers.
- **Idempotent + versioned**: generated files carry a parseable `<!-- docir:vX -->`
  stamp. A skill file is docir's entirely and is rewritten wholesale; an
  `AGENTS.md` block is replaced-not-duplicated and a *foreign* `AGENTS.md` is
  never rewritten by `update` (only appended to when `--agent agents` is asked
  for). `update` auto-detects installed files and reports `vOLD → vNEW`.

**It does not go through the Dispatcher/daemon.** The module owns no index/DB
state and does not participate in the shared unit-of-work (ADR-0002), so the CLI
builds the service directly via `agents.api.build_agent_service(version)` and
runs it in-process — the same pattern as `version` and `daemon serve`. Routing a
filesystem copy through the socket, engine, and migrations would be actively
wrong. The module is therefore **clean**: it introduces **no `platform → agents`
baseline edge** and depends only on `platform.errors`.

## Consequences
- Easier: `docir agent install` is a one-command onboarding; the guide is now
  shipped in the wheel and versioned with docir, so `update` refreshes it after
  an upgrade. `AGENTS.md` covers every non-Claude assistant.
- Chosen cost: this is a full module (its own ADR, `CONTRACT.md`, tach entries)
  for what is essentially file templating — deliberately, over a lighter
  `platform` capability, to keep a clean bounded context with a documented
  public contract.
- Deviation from the "single command vocabulary" thesis: `agent` commands bypass
  the Dispatcher. This is scoped to operations with no index state and is noted
  in the module `CONTRACT.md`; it does not widen to document/tag/maintenance.
- Scoped out: Cursor/Copilot/Windsurf-native files, and any environment
  sniffing — targets are chosen explicitly by `--agent`. Adding a native format
  later is a new entry in `AGENT_TARGETS` plus a render branch, nothing more.
- Follow-up: `docs/AGENT_GUIDE.md` becomes a thin pointer to the packaged
  template so the two never drift.
