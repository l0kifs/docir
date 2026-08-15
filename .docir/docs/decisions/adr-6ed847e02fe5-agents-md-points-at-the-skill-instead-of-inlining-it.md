---
code:
- src/docir/modules/agents/**
- tests/modules/agents/**
- tests/entry_points/test_e2e_agent.py
created: '2026-08-15'
description: Why the AGENTS.md block became a pointer (description + path) and now
  always installs the skill it names, instead of embedding a second copy of the guide.
id: adr-6ed847e02fe5
related:
- kind: refines
  to: adr-3a2d5ee7bc84
status: accepted
tags:
- agents
- docs
- cli
title: AGENTS.md points at the skill instead of inlining it
type: decision
updated: '2026-08-15'
---

## Context
adr-3a2d5ee7bc84 gave the two instruction targets one template and two
independent flows: `claude` wrote the packaged guide to a skill file, and
`agents` wrote *the same guide again*, frontmatter stripped, into a marker block
in `AGENTS.md`. Picking `agents` alone wrote no skill file at all.

Three problems followed from the duplication rather than from any bug.

The guide is ~500 lines. A repo installing both targets committed it twice, and
the copies could disagree between an install and the next `docir agent update`.
This is the failure mode docir exists to prevent, reproduced in docir's own
output: the same content in two places, where nothing reads both and only one
gets refreshed.

The cost also scales the wrong way. A second skill (documentation-writing rules,
alongside the CLI guide) would double the block — every skill docir ships would
be inlined in full into a file whose whole job is to be read first.

And `AGENTS.md` is read by assistants that do not load Claude skills, so what
they needed was not the guide's body but the answer to *should I read further* —
which is exactly what the skill's frontmatter `description` already says.

## Decision

`AgentForm.EMBEDDED` becomes `AgentForm.POINTER`, and the block becomes an index:
the skill's `description` **verbatim** plus a repo-relative link to the file.
`AgentTarget` gains `points_to`, the names of the `SKILL`-form targets a pointer
refers to — one field that is both the block's content and the target's
dependency, so the two cannot drift.

Selecting a pointer target therefore installs the skills it names. `docir agent
install --agent agents` writes the skill *and* the block; `docir agent update`
expands the same way, so a block whose skill file was deleted is healed rather
than left naming nothing.

The description is copied, not summarised. It is a rendered projection of one
source — the packaged template — regenerated on every write, which is the
single-source-of-truth shape rather than a second copy of it.

Load-bearing details. The path is joined from `relative_path` with `/`, never
`os.sep`: the block is committed and read on every OS. `MARK_POINTER`
(`<!-- docir:pointer -->`) marks the new form, so a block written before it is
identifiable by that marker's *absence* — not by matching the old guide's
wording, which would rot with the template. And the description is lifted by
regex, in `domain/`, which this module declares with no dependencies at all
(`tach.toml`) — not even the error taxonomy. So the lift *reports absence*
(`str | None`) and the application layer is what refuses to render: a block
naming a file without saying when to open it looks like a finished install.

## Consequences
- Easier: `AGENTS.md` goes from ~500 lines to ~8, and stays that size as docir
  ships more skills. Migration is free — the existing marker block is replaced
  wholesale on the next `docir agent update`, which reports the shrinkage.
- Chosen cost: a non-Claude assistant no longer has the guide in its context and
  must open the linked file. That is the trade — a lazy read that can be skipped,
  against a copy that goes stale. The verbatim description is the mitigation: the
  trigger conditions stay in `AGENTS.md` even when the body does not.
- `--global` is unchanged and still refuses `agents`: the block names a
  repo-relative path, which cannot address a skill under `~/`.
- Scoped out: a second skill template. `points_to` is a tuple and the block
  renders one entry per skill, so adding one is a template-catalogue change in
  `infra`, not another change to this shape.
