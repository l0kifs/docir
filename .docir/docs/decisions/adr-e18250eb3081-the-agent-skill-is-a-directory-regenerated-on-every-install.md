---
code:
- src/docir/modules/agents/**
created: '2026-08-25'
description: Why the packaged CLI guide became SKILL.md plus one-level-deep reference
  files, and why installing a skill sweeps the files a build no longer ships.
id: adr-e18250eb3081
related:
- kind: refines
  to: adr-3a2d5ee7bc84
- adr-6ed847e02fe5
- adr-735ba7f6209b
status: accepted
tags:
- agents
- docs
title: The agent skill is a directory, regenerated on every install
type: decision
updated: '2026-08-26'
---

## Context

The packaged CLI guide (`templates/skill.md`) reached 764 lines / ~11.8k tokens.
Anthropic's skill-authoring guidance puts the eagerly-loaded SKILL.md body under
**500 lines** and budgets that level at **under 5k tokens**; bundled files cost
nothing until read. docir's guide was 2.4x over, and every session that triggered
the skill paid all of it to learn how to run `docir context`.

The rules that constrain a split, from the same guidance:

- references must be **one level deep** from SKILL.md — a file reached through
  another referenced file gets previewed (`head -100`), not read;
- a reference file over 100 lines needs a **table of contents**, so a partial
  read still shows its scope;
- group **by task**, because the link text is what the assistant routes on.

## Decision

A skill is a **directory**, not a file: `templates/<name>/SKILL.md` plus the
reference files it links. `TemplateProvider.template` returns every `.md` keyed
by its path relative to the skill directory, and `AgentTarget.directory` is what
the skill owns outright.

The CLI guide splits into an entry point (~255 lines) carrying the everyday loop
— when to use, core loop, read, write, hard rules, types — and six task-grouped
files under `reference/`: setup, retrieval, schema, maintenance, publishing,
troubleshooting. Six rather than five because getting the entry point under
budget requires lifting `--expr`, `--also` and `--explain` out of the read
section, and those are one task, not a remainder.

**Installing a skill regenerates its directory.** Every packaged file is written
and every `.md` under that directory the build does not ship is deleted. This is
the rule `docir build` already applies to `--out`, for the same reason: a
reference file a release renamed would otherwise stay on disk, linked from
nothing, and still answer. Stale instructions are worse than absent ones.

## Consequences

- The sweep is bounded by the skill's own directory, so a second skill and
  anything else in the tree are untouched. It is reported in `InstalledFile.removed`,
  because it is the one part of an install that destroys something.
- `action` aggregates over the directory: a release that only adds a reference
  file is `updated`, though `SKILL.md` differs by nothing but its stamp. A
  per-file answer would report `unchanged` for a skill that gained a chapter.
- One row per target, not per file — seven rows repeating one version transition
  would bury the answer the caller wants.
- Every file carries the version stamp, so a hand-edited reference is
  distinguishable from a shipped one.
- The guide-vs-CLI sweep joins the template's files into one text: a command
  moved from the entry point into `reference/` has not stopped being documented.
- Cost: sibling cross-references (setup -> schema) are a second hop. They are
  tolerable only because every reference file is also linked from SKILL.md, so
  nothing is reachable *only* by nesting; a guard asserts that.

## Verified

The single-file → directory migration was exercised end to end: a repo carrying the
765-line v0.18 `SKILL.md` and no `reference/` runs `docir self upgrade --no-package`
and ends with a 256-line entry point, six reference files and a 0.18.0 → 0.19.0
transition. Pinned by `test_it_grows_a_single_file_skill_into_a_directory`.

That run also found the defect this change had shipped: `self upgrade` and `docir agent
update` each serialized `InstalledFile` themselves, so the upgrade reported the install
without naming the reference files it wrote. There is now one `_setup_file`, and
`test_upgrade_reports_an_install_the_same_way_agent_update_does` compares the two
commands' JSON keys.
