---
paths:
  - "src/docir/modules/agents/**"
  - ".claude/skills/**"
---

# The agents module — installed skills and the AGENTS.md block

This module writes files into *other* people's repositories. Edit the packaged template, never this repo's installed copies, then run `docir agent update`.

- **`docir agent install/update` bypasses the daemon/dispatcher on purpose (adr-3a2d5ee7bc84).** The
  `agents` module installs AI-assistant instruction files (a Claude skill, and an `AGENTS.md`
  block linking it) from one packaged template *directory*
  (`modules/agents/infra/templates/skill/` — `SKILL.md` plus the `reference/*.md` it links,
  the canonical guide; edit it there, not `docs/AGENT_GUIDE.md`, which is now a pointer).
  Installing a skill **regenerates** that directory: every packaged file is written and every
  `.md` under it this build does not ship is deleted and reported (adr-e18250eb3081), because a
  reference file a release renamed would stay on disk, linked from nothing, and still answer.
  The entry point is held under 500 lines by a test — past that, an assistant pays the whole
  guide to learn one command. It touches
  no index/DB, so the CLI builds the service directly via
  `agents.api.build_agent_service(__version__)` and runs it in-process — like `version` and
  `daemon serve`, not through the `RequestExecutor`/`Dispatcher`. Generated files carry a
  `<!-- docir:vX -->` stamp so `update` reports a version transition; a foreign `AGENTS.md` is
  never rewritten (only docir's marker block is).

- **There are two skills, and the second is opt-in (adr-735ba7f6209b).** `claude` teaches the CLI;
  `claude-writing` (`.claude/skills/docir-writing/SKILL.md`, template `writing.md`) teaches how to
  write the documents — one name per concept, one purpose per document, state each fact once and
  link it, and keep each `##` section under ~1,200 chars. That last number is `MAX_CHUNK_CHARS`,
  not a style preference; the skill deliberately carries **no word limit**, because the
  topic-based standards reject one and `similarity_lint.py` already warns on size. It stays out
  of `DEFAULT_AGENTS` since both skills match the same work and a repo that did not ask for the
  second should not pay its context. `TemplateProvider.template(name)` is a keyed catalogue, so a
  third skill is a template plus a catalogue entry — do not grow either skill into a grab-bag.

- **The `AGENTS.md` block points at the skills; it does not contain them (adr-6ed847e02fe5).** It
  carries the template's frontmatter `description` verbatim plus a repo-relative link, so docir's
  own output stops being the duplication docir exists to prevent — and a second skill costs a line
  rather than another ~500. It indexes every skill installed under the same root, and installing a
  skill refreshes an installed block in the same run — so the optional skill is listed once it
  exists without the index dragging it in.
  Three details hold it up. `AgentTarget.points_to` is the block's *floor* —
  content and install dependency both — so selecting `agents` writes the skill too (on `update` as
  well, which is what heals a block whose skill was deleted) and the two cannot disagree. The path
  comes from `posix_path`, never `os.sep`, because the block is committed and read on every OS.
  And a legacy block is identified by the *absence* of `MARK_POINTER`, not by matching the old
  guide's wording — which would rot the moment the template changed.
