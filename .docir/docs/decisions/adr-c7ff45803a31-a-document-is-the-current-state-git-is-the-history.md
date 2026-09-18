---
code:
- src/docir/modules/agents/infra/templates/writing/SKILL.md
- src/docir/modules/agents/infra/templates/skill/SKILL.md
code_baseline:
  src/docir/modules/agents/infra/templates/skill/SKILL.md: 9514ea0b4cd1
  src/docir/modules/agents/infra/templates/writing/SKILL.md: c44b11d34e7a
created: '2026-09-18'
description: Why the writing skill forbids appending a dated section for every change,
  and why that rule ships as prevention rather than as a new lint finding.
id: adr-c7ff45803a31
owner: maintainer
related:
- adr-735ba7f6209b
- adr-49bb8cc48938
status: proposed
tags:
- agents
- docs
- integrity
title: A document is the current state; git is the history
type: decision
updated: '2026-09-18'
verified: '2026-09-18'
verified_code:
  src/docir/modules/agents/infra/templates/skill/SKILL.md: 9514ea0b4cd1
  src/docir/modules/agents/infra/templates/writing/SKILL.md: c44b11d34e7a
verified_content: 79225f87cda8
---

## Decision

The `docir-writing` skill gains a rule: a document says what is true now, and git says what
was true before. When something changes, the section that is now wrong is **edited**, not
answered beside with a dated one.

It is prevention only. No new check and no new lint kind.

## The failure it names

Agents append. `--append-section` is the cheapest correct-looking write — it destroys
nothing, so it never refuses — and over a few sessions a document becomes a log of its own
life: the original text, then what changed, then what changed after that.

Two costs, and the second is the one that is not obvious. The body grows against a ceiling
the store sets per type. And the superseded half keeps being *retrieved*, because the index
has no idea a later paragraph overruled an earlier one — so a reader gets an answer that
was true in July.

## Measured

Across this store's 235 documents: median body 3,187 characters, 21 past the 8,000-character
`scope-creep` threshold, largest 38,954 — five times it. The documents at the top are the
ones that grew by appending. One 29,099-character reference carries three consecutive
`Follow-up — … (2026-07-26 / -27 / -28)`; others carry `Delta pass — 2026-07-29`,
`Third round, 2026-07-30`, `What moved since 2026-08-03`, `Amendment: … (2026-08-13)`.

None of them had a purpose problem, which is what rule 2 would have caught. They were
keeping a diary.

## Why prevention only

`docir lint --deep` already reports the symptom — `scope-creep` on 15 documents here,
`oversized-section` on 128 — so nothing is invisible today. What is missing is the *cause*,
and the honest place for that is the skill: the agent is told the rule while it writes,
which is what this skill is for.

A Tier 2 finding on heading text was the alternative and was refused. The signal would be a
date or a word like "follow-up" in a `##`, and the corpus says that fires on correct usage:
`Resolution` appears on 82 documents and is an issue's terminal state, not a log entry, and
a dated measurement heading is a fact worth keeping. That is `unresolved-mention`'s shape
exactly — a check whose every finding here was correct usage — and [[adr-49bb8cc48938]]'s
tier rules say a heuristic that fires on the product's own defaults does not earn a tier.

The door stays open in the cheaper direction: `scope-creep` already fires on the documents
this is about, and could gain a second sentence naming the cause without inventing a
predicate.

## What is not the failure

A terminal state is part of what a document is for — an issue's `Resolution`, a decision's
`Consequences`. So is a date inside prose: "measured on 2026-08-12" is the claim, not a log
entry. The rule is about a heading addressed to a *moment* rather than to a subject.

Replacing a whole document stays an edge, `supersedes`, which `docir context` can follow
and a paragraph cannot.

## Consequences

The two skills now say the same thing about `--append-section`, and neither names the
other. The CLI skill ranked body edits safest-to-riskiest and called appending "the default
choice" — true about what each one can destroy, and read as advice for years. It now says
the ranking is about damage and that the choice is about what you are doing.

It says that **on its own**, without pointing at this rule. `docir-writing` is opt-in and
absent from `DEFAULT_AGENTS`, so a reference from the always-installed skill would name a
file most repositories do not have. The division stands: the `docir` skill is how to *use*
docir, `docir-writing` is how to write and maintain the documents, and guidance that
belongs in both is written twice rather than linked once. That is the one place this store
accepts a duplicate, and it is the same reason `reference/troubleshooting.md` carries the
feedback skill's argument for the repositories that decline it.

This store's own 21 over-length documents are left as they are. Rewriting them is a corpus
pass, not part of shipping the rule, and they are the evidence the rule cites.
