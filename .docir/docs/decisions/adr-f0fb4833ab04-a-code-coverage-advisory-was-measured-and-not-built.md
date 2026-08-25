---
code:
- src/docir/modules/documents/domain/services/similarity_lint.py
created: '2026-08-25'
description: Prose naming a source path is not evidence a document governs it — the
  examples, the historical records and the inventories are indistinguishable from
  the text.
id: adr-f0fb4833ab04
owner: maintainer
related:
- adr-bd7c4f3c5764
- kind: refines
  to: adr-f14682e3f4d6
status: accepted
tags:
- integrity
- cli
title: A code-coverage advisory was measured and not built
type: decision
updated: '2026-08-25'
---

## Context

Four of the six documents 0.18.0 made stale carried **no `code:` glob**, so
`query --code $(git diff --name-only)` — the review notice docir ships — could not reach them.
A document about a surface that does not declare the surface is invisible to the one mechanism
that would have named it. The obvious fix was a Tier 2 advisory: a document that *describes*
code and declares none.

The problem is deciding what "describes code" means without asking the author. The one signal
available is the document's own prose: a body naming `src/...` is evidence its writer knew
which code it was about.

## Measured

On docir's own corpus, 173 documents: 80 name no path, 30 name paths and declare globs, and
**63 name paths and declare none** — 36% of the corpus, which is noise, and 56 of those are
issues. An issue is a problem report, not a claim of governance, and a resolved one needs no
glob at all.

Restricted to *live* `architecture`/`decision`/`reference`, it drops to seven. That is a usable
count, and inspecting all seven is what killed it:

| document | what it names | should it declare? |
|---|---|---|
| `arch-39314a23ba7f` | `src/auth/**`, `tests/test_auth.py` | **no** — those are the *examples* it uses to teach the `code:` field |
| `ref-a6db21f52427`, `ref-1509d5dbb4c3`, `ref-9e4cce368b80` | a benchmark script, probe paths | **no** — historical records, naming what was true once |
| `ref-301bcc84b75c`, `ref-32cb4f874fbe`, `ref-cbf147832c37` | 11–24 paths each | cross-cutting inventories, not governance |

Zero clear true positives out of seven.

## Decision

Not built. **Prose naming a path is not evidence of governance**, and the three ways it can be
something else — an example teaching the field, a historical record, a cross-cutting inventory
— are indistinguishable from the text. What they share is the cost of being wrong: `code:` is a
claim, so a false positive here asks an author to assert something untrue about their corpus.

That distinguishes it from the advisories Tier 2 already carries. `oversized-section` reports a
mechanical fact — the chunker split this section, here is what nothing can address. This would
report a guess at intent, and intent is the one thing only the author has.

## What was done instead

The six stale documents were fixed by hand and now declare globs, so the next release's sweep
reaches them. The general problem — a document nobody thought to annotate — stays open and
manual, which is the same shape as `--verified`: a signal only a person can emit, and one that
is worthless the moment something emits it automatically (adr-bd7c4f3c5764).

What would reopen this is a discriminator that separates governance from mention. Nothing in
the text is one.
