# docir — Agent Guide

The canonical agent guide now **ships with docir** as a packaged instruction
template and is installed into a project (or globally) with one command — it is
no longer maintained as a copy here (see ADR-0008 — `docir get adr-3a2d5ee7bc84`).

## Install it

```bash
docir agent install                        # Claude Code skill → ./.claude/skills/docir/SKILL.md
docir agent install --agent claude-writing # opt-in: how to WRITE the documents
docir agent install --agent claude-feedback # opt-in: draft a docir defect report for a human to file
docir agent install --agent agents         # the skill, plus an AGENTS.md block linking it
docir agent install --global               # install the skill under ~/ for every project
docir agent update                         # refresh installed instructions after upgrading docir
```

`install` is idempotent; `update` auto-detects what is installed, refreshes it to
the running docir version, and never rewrites a foreign `AGENTS.md` (it only
replaces docir's own `<!-- docir:start/end -->` block, or appends one when you
pass `--agent agents`).

The `AGENTS.md` block is an **index, not a copy**: each skill's description
verbatim and a link to its file (see `docir get adr-6ed847e02fe5`). Requesting it
installs the skill it names, so the link always resolves — including under
`docir agent update`, which rewrites a skill someone deleted. It lists whichever
skills are installed, so adding the writing skill adds a line rather than a copy.

## Three skills

| target | file | covers |
|---|---|---|
| `claude` (default) | `.claude/skills/docir/SKILL.md` | driving the CLI: the read/write loop, the schema, the hard rules |
| `claude-writing` (opt-in) | `.claude/skills/docir-writing/SKILL.md` | writing the documents: naming, one purpose per document, linking instead of repeating, section length |
| `claude-feedback` (opt-in) | `.claude/skills/docir-feedback/SKILL.md` | reporting a docir defect or missing capability upstream instead of working around it: drafts the report as a local file for a human to review and file, and never sends anything |

Neither opt-in skill is installed by default. The writing skill matches the
same work as the first, so a repo that does not want it should not load it
every session (`docir get adr-735ba7f6209b`). The feedback skill ends in
something leaving the machine, so only a human who chose it installs it — docir
suggests it and never selects it (`docir get adr-7144cf291b1a`).

## Source of truth

The content lives in the packaged template directories
[`skill/`](../src/docir/modules/agents/infra/templates/skill),
[`writing/`](../src/docir/modules/agents/infra/templates/writing) and
[`feedback/`](../src/docir/modules/agents/infra/templates/feedback). Each holds a
`SKILL.md` plus the `reference/*.md` files it links (adr-e18250eb3081).
Edit them there — a skill installs its directory verbatim and sweeps what the
build no longer ships, and the `AGENTS.md` block quotes each frontmatter
`description` and links the entry point.
