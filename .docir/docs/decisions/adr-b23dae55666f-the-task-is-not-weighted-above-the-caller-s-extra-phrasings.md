---
code:
- src/docir/modules/indexing/domain/scoring.py
created: '2026-08-24'
description: Weighting the literal task removes --also's gain along with its risk,
  because an extra query is powerful exactly to the degree it can outvote the task.
id: adr-b23dae55666f
owner: maintainer
related:
- adr-27c63ad02695
- issue-fd086c0c6ab0
- adr-46b69a581c65
status: accepted
tags:
- retrieval
- cli
title: The task is not weighted above the caller's extra phrasings
type: decision
updated: '2026-08-24'
---

## Context

`--also` shipped with two claims about its failure mode, both argued and neither measured: that
a bad hypothetical alone would be catastrophic, and that one fused with the task would degrade
gracefully. The first was right. The second was wrong, and it was the one the guidance rested on.

Measured on docir's own corpus, eight judged tasks, the "bad" hypothetical fluent and in the
right register but about a different part of the system — an agent that wrote a confident answer
to the wrong question, not one that misread the task:

| configuration | recall@5 | MRR |
|---|---|---|
| task only | 0.88 | 0.63 |
| task + correct hypothetical | 1.00 | 0.75 |
| task + wrong hypothetical | **0.25** | 0.17 |
| wrong hypothetical only | 0.06 | 0.03 |
| task + correct + wrong | 0.69 | 0.50 |

The task string does not anchor anything: it scored 0.88 alone and 0.25 with a bad phrasing
beside it. A correct phrasing does not rescue a wrong one either.

## Decision

**The caller's task is not weighted above its `--also` strings**, and the reason is measured
rather than argued. Weighting was the obvious fix and it does not fix anything:

| task weight | correct | wrong |
|---|---|---|
| ×1 | **1.00** | 0.25 |
| ×2 | 0.88 | 0.75 |
| ×3 | 0.88 | 0.81 |
| ×5 | 0.88 | 0.88 |

At ×2 and above the *gain disappears with the risk*. There is no weight that keeps one and
removes the other, because they are the same mechanism: an extra query is powerful exactly to
the degree it can outvote the task, and safe exactly to the degree it cannot. At ×5 the flag
does nothing in either direction.

qmd weights its literal query ×2, which reads like a precedent and is not one: its expansions
are machine-written and systematically worse than the query, so a correction makes sense. Here
every string is the caller's, and the sweep says the correction costs the whole feature.

## Consequence: guidance, not machinery

The mechanism stays at equal weight and the *advice* changes. `--also` is for a caller who could
defend the answer it is guessing — it has read the code, or already retrieved the topic once.
An exploring caller that could not say what the document will claim sends the task alone.

That is an uncomfortable place to leave a feature and it is the honest one. The upside is +0.12
and the downside −0.63, so it breaks even only if the caller is right more than 84% of the time
— which is a judgement about the caller, and the caller is the only party who can make it.

## What would reopen this

A fusion shape that bounds one query's share of the result set — no single query claiming more
than half the slots — is the one idea that might keep the gain and cap the loss. Untested.
Weighting is answered; slot-capping is not.
