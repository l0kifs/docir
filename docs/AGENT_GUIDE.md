# docir — Agent Guide

The canonical agent guide now **ships with docir** as a packaged instruction
template and is installed into a project (or globally) with one command — it is
no longer maintained as a copy here (see
[ADR-0008](adr/ADR-0008-agent-instruction-scaffolding.md)).

## Install it

```bash
docir agent install                 # Claude Code skill → ./.claude/skills/docir/SKILL.md
docir agent install --agent agents  # also write an AGENTS.md block (cross-assistant)
docir agent install --global        # install the skill under ~/ for every project
docir agent update                  # refresh installed instructions after upgrading docir
```

`install` is idempotent; `update` auto-detects what is installed, refreshes it to
the running docir version, and never rewrites a foreign `AGENTS.md` (it only
replaces docir's own `<!-- docir:start/end -->` block, or appends one when you
pass `--agent agents`).

## Source of truth

The guide's content lives in the packaged template
[`src/docir/modules/agents/infra/templates/skill.md`](../src/docir/modules/agents/infra/templates/skill.md).
Edit it there — the Claude skill installs it verbatim and `AGENTS.md` embeds the
same body with its frontmatter stripped.
