---
code:
- src/docir/modules/agents/infra/templates/writing.md
- src/docir/modules/agents/domain/targets.py
- src/docir/modules/agents/infra/template_provider.py
created: '2026-08-15'
description: Why documentation-writing rules ship as their own opt-in skill rather
  than a section of the CLI guide, and why the length rule is a section limit rather
  than a word count.
id: adr-735ba7f6209b
related:
- kind: refines
  to: adr-3a2d5ee7bc84
- adr-6ed847e02fe5
- kind: depends_on
  to: adr-927aa43d9635
status: accepted
tags:
- agents
- docs
title: A second, optional skill for how to write the documents
type: decision
updated: '2026-08-15'
---

## Context
The packaged guide teaches an agent to *drive* docir — the commands, the schema,
the read/write loop. Nothing taught it what to put in a document, so the corpus
quality rested on whatever the agent already believed about documentation.

`docir lint --deep` does check two of the properties that matter: near-duplicate
documents (cosine ≥ 0.9, unlinked) and oversized ones (8,000 characters). But a
check is a verifier, not a teacher. An agent that never learned the rule produces
the finding every time and learns it only by being corrected — which is the
expensive order, and only works when a human reads the output.

Two more properties nothing measures at all: whether the corpus names one concept
one way, and whether a document does one job. Both are cheap to follow while
writing and expensive to repair afterwards, because repairing them means
splitting documents and rewriting every reference.

## Decision
Ship the rules as a **second, opt-in skill**: target `claude-writing` →
`.claude/skills/docir-writing/SKILL.md`, from its own packaged template
`writing.md`. `TemplateProvider` becomes a keyed catalogue (`template(name)`)
and `AgentTarget` names its template, so a skill is a catalogue entry plus a
file rather than a branch in the renderer.

**Separate, not a section of the guide.** The two are read at different moments —
one when driving the CLI, one when composing prose — and a skill is loaded by its
`description`, so merging them means every session that touches docir at all
loads both. That is also the rule the new skill teaches, applied to itself.

**Opt-in.** It is absent from `DEFAULT_AGENTS`; both skills match the same work,
so a repo that did not ask for the second one should not pay its context. The
`AGENTS.md` index lists it once installed but never drags it in — which is why
`points_to` stayed the pointer's *floor* rather than becoming its full contents.

## The rules, and what backs them
Four rules, three of them well supported and one deliberately reshaped.

**One name per concept** and **state each fact once** are standard: style guides
put terminology consistency first, and single-sourcing exists precisely because
the second copy is the one that goes stale. docir's own answer to the second is a
typed `related` edge, which is why the skill teaches linking rather than quoting.

**One purpose per document** is topic-based authoring's "one topic, one idea"
and Diátaxis's "do not mix the four modes". docir already encodes it: a
document's `type` declares its purpose, so the rule reads as *write what the type
says* rather than as an abstraction.

**Length is the reshaped one.** A round "under 1,000 words" has no support — the
topic-based standards say explicitly that a topic runs as long as its subject
requires, and that chunking follows content rather than word counts. What docir
*does* have is a measured number in the other direction: `MAX_CHUNK_CHARS` is
1,200 because the embedding model reads ~1,900 characters (adr-927aa43d9635), so
a longer `##` section is split mid-paragraph and retrieves worse. The rule is
therefore a *section* limit, which is real, plus "bound the document by its
purpose, not by counting", which is rule 2 doing the work.

## Consequences
- The rules exist in two tiers on purpose: the skill prevents, `docir check` and
  `docir lint --deep` detect. The overlap with the existing lint checks is the
  design, not redundancy — a finding should be a rule the writer already knew.
- Chosen cost: a repo that installs both skills loads both descriptions in every
  session. That is the price of keeping each one single-purpose, and the reason
  the second is opt-in rather than default.
- The catalogue makes a third skill cheap — a template plus a target entry — so
  the pressure to grow one skill into a grab-bag is gone.
- Scoped out: making any of these machine-checked. Terminology drift and
  purpose-mixing are judgement calls, and a Tier 1 error on either would fail
  builds over prose (the argument the staleness and schema-drift rules already
  make). If they ever land, they land as Tier 2 advisories.
