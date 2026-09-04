---
code:
- src/docir/modules/documents/domain/services/graph_checks.py
- src/docir/modules/documents/domain/entities/document.py
- src/docir/platform/persistence/ports.py
created: '2026-09-04'
description: 'Why check stopped reading the mention graph and gained an isolated:
  reason instead — a judgement about a queue must not empty the queue.'
id: adr-e98749aa457d
owner: maintainer
related:
- issue-77a09761e1d4
- kind: refines
  to: adr-e86c5040d626
status: accepted
tags:
- architecture
- cli
- integrity
title: The orphan exemption is a recorded field, not a prose mention
type: decision
updated: '2026-09-04'
---

`orphan` read two graphs: the authored `related:` edges and the mention edges derived from
prose. Reading the derived one made the finding self-clearing (issue-77a09761e1d4) — an orphan
triage is a list of orphan ids, so writing one closed every id it listed.

## The decision

`orphan` reads `related:` alone. A document also carries `isolated:` — a free-form reason it is
*meant* to stand alone — and a document that has one is not reported.

    docir update <id> --set-related <other>:refines        # it was unwired
    docir update <id> --set-isolated "scope deferred"      # it stands alone by design
    docir query --expr "isolated"                          # audit every exemption
    docir update <id> --set-isolated ""                    # withdraw one

## Why a field and not a mention

The two states a triage distinguishes — "correctly isolated" and "still unwired" — are written
in identical characters when they are written as prose. No filter over a body can separate an id
that is being exempted from an id that is being listed as outstanding, because the difference is
a conclusion somebody reached, not a property of the text.

A field records the conclusion. It is also the thing the six correctly-isolated documents in
issue-77a09761e1d4 actually had in common, which the mention graph was standing in for by
accident.

## Why a reason and not a boolean

`isolated: true` records that somebody silenced the warning. It does not record what they
concluded, so the next reviewer cannot tell a decision from a drive-by, and re-deciding costs
the same as deciding did. The field follows `owner:` — free text, empty means absent.

It follows `owner:` in one more way that was almost got wrong here: writing it stamps
`updated`, as every flag `update` carries does. The rule that a rewrite must not launder the
review clock adr-bd7c4f3c5764 depends on governs the writes nobody asked for — a tag rename,
`check --fix`, a forced delete's unlink — not an edit somebody typed. Three docstrings claimed
the opposite until a test on an advancing clock disagreed; on the suite's frozen clock the
claim and its negation are the same assertion.

## What this gives back, and what it costs

The false positive that put mentions in the check is real: before them, `orphan` fired on every
document whose author linked it in a sentence, which is half of why `--strict` stopped failing
on warnings. It is now answered by an exemption somebody wrote on purpose rather than by a side
effect of where an id was typed.

Measured on this store the day it shipped: 194 live documents, and removing prose from the check
restores **zero** orphans — every live document here carries an authored edge. The cost is
bounded by how many documents a corpus links only in prose, and the remedy for each is the edge
it was missing.

## What survives, and what an older build sees

The mention graph is unchanged. It still feeds `docir context` expansion, the `mentions` /
`mentioned_by` lists on `get`, and the Tier 2 `unresolved-mention` advisory — none of which
gates anything. What it lost is its only Tier 1 reader, so `MentionRepository.all_resolved` is
gone with it.

`isolated:` is additive frontmatter. A docir before this release reads a document carrying it
without complaint and simply cannot see it — but a *write* through that build drops the key,
because it renders frontmatter from the fields it knows. Withdrawing an exemption by downgrade
is the failure mode, and it is visible in `git diff`.
