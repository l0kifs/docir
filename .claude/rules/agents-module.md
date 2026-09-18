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

- **There are three skills, and two are opt-in (adr-735ba7f6209b, adr-7144cf291b1a).** `claude`
  teaches the CLI; `claude-feedback` (template `feedback/`) teaches an agent to report a docir
  defect *upstream* instead of papering over it with a wrapper script or a project rule — it only
  ever drafts a file, and a human files it, which is why it is absent from `DEFAULT_AGENTS` and
  suggested instead from the two Rich renderers a person setting docir up actually reads
  (`render_init`, `render_setup` — never the JSON, where the suggestion would reach the wrong
  reader). Its counter-pressure ships even to repos that decline it, as a section of the default
  skill's `reference/troubleshooting.md`.
  `claude-writing` (`.claude/skills/docir-writing/SKILL.md`, template `writing/SKILL.md`) teaches
  how to write the documents — one name per concept, one purpose per document, **one point in
  time**, state each fact once and link it, and keep each `##` section under ~1,200 chars. That
  last number is `MAX_CHUNK_CHARS`, not a style preference; the skill deliberately carries **no
  word limit**, because the topic-based standards reject one and `similarity_lint.py` already
  warns on size. "One point in time" is the rule against appending a dated section per change
  (adr-c7ff45803a31): agents reach for `--append-section` because it destroys nothing, and a
  document becomes a log of its own life — 21 of this store's 235 documents are past the
  `scope-creep` threshold and the largest is five times it. It ships as **prevention only**, and
  a Tier 2 finding on heading text was refused rather than forgotten: `Resolution` appears on 82
  documents and is a terminal state, so the predicate would fire on correct usage the way
  `unresolved-mention` does. The CLI skill carries the same correction **without naming the
  writing skill**: `docir-writing` is opt-in, so a cross-reference from the always-installed
  skill points at a file most repos do not have. Every such rule has to stand on its own
  wherever it appears — the CLI skill's safest-to-riskiest ranking of body edits is about
  what each one can *destroy*, and calling appending "the default choice" is what read as
  advice. It stays out
  of `DEFAULT_AGENTS` since both skills match the same work and a repo that did not ask for the
  second should not pay its context. `TemplateProvider.template(name)` is a keyed catalogue, so a
  fourth skill is a template plus a catalogue entry — do not grow any of them into a grab-bag.

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
