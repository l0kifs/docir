---
created: '2026-09-04'
description: Naming an id in prose cleared the orphan warning, so writing the triage
  of the orphan list closed every id on it — including the ones the triage said were
  still unwired.
id: issue-77a09761e1d4
owner: maintainer
related: []
status: resolved
tags:
- cli
- integrity
title: The orphan queue empties itself when somebody triages it
type: issue
updated: '2026-09-04'
---

`docir check` reports `orphan` for a document with no `related:` edge that no other document
names. Both halves were readable, and the second half read the prose: an id written anywhere
in any body cleared the finding.

So the queue emptied itself the moment somebody wrote down what was in it.

## What was observed

On a corpus of ~418 documents (2026-08-31), `docir check` reported 12 orphans. Two were wired
properly. The remaining ten were triaged into a section of one architecture document — a list
of ids with a diagnosis beside each. `docir check` then reported zero.

Six of the ten were correctly isolated: a deferred scope decision, a flow whose body explains
that no acceptance criterion references it, a decision that wants a `code:` glob rather than an
edge. Four were genuinely unwired and stayed unwired. All ten stopped warning, and the four had
no mechanical queue left — only a paragraph in a document nothing checks.

## Why the prose signal cannot work

The finding asks "has anybody connected this?" and the mention graph answers "has anybody typed
this id?". Those come apart hardest in exactly the document that matters: an orphan triage is a
list of orphan ids, so writing it clears every id on the list, including the ones it concludes
are still unwired. It also clears the triage document itself, which was the third orphan in the
reproduction.

The two states are written in the same characters. "This id is fine standing alone" and "this id
still needs an edge" are both `adr-3f9a2b1c7d4e` in a sentence, so no filter over prose can
separate them — the distinction is a judgement, and a judgement has to be recorded as one.

## Reproduction

Three documents with no edges: `docir check` reports three orphans. Write a body into the third
naming the first two. `docir check` reports none.
