# docir — Agent Guide

The canonical agent guide now **ships with docir** as a packaged instruction
template and is installed into a project (or globally) with one command — it is
no longer maintained as a copy here (see ADR-0008 — `docir get adr-3a2d5ee7bc84`).

## Install it

```bash
docir agent install                        # Claude Code skill → ./.claude/skills/docir/SKILL.md
docir agent install --agent claude-writing # opt-in: how to WRITE the documents
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

## Two skills

| target | file | covers |
|---|---|---|
| `claude` (default) | `.claude/skills/docir/SKILL.md` | driving the CLI: the read/write loop, the schema, the hard rules |
| `claude-writing` (opt-in) | `.claude/skills/docir-writing/SKILL.md` | writing the documents: naming, one purpose per document, linking instead of repeating, section length |

The second is deliberately not installed by default — both match the same work,
so a repo that does not want it should not load it every session
(`docir get adr-735ba7f6209b`).

## Source of truth

The content lives in the packaged templates
[`skill.md`](../src/docir/modules/agents/infra/templates/skill.md) and
[`writing.md`](../src/docir/modules/agents/infra/templates/writing.md).
Edit them there — a skill installs its template verbatim, and the `AGENTS.md`
block quotes each frontmatter `description` and links the file.
