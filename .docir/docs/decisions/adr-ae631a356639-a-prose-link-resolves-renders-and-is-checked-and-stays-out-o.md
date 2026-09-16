---
code:
- src/docir/modules/publishing/infra/rendering.py
code_baseline:
  src/docir/modules/publishing/infra/rendering.py: 16d9f4392c5b
created: '2026-09-11'
description: Why [[...]] cross-references now resolve against ids, filename stems
  and title slugs, why the unresolved ones are a Tier 1 warning where unresolved mentions
  are not, and why they still feed no check.
id: adr-ae631a356639
owner: maintainer
related:
- kind: refines
  to: adr-289e788719a7
- adr-e86c5040d626
- adr-e98749aa457d
- arch-ad342aae8293
status: accepted
tags:
- architecture
- cli
- integrity
title: A prose link resolves, renders and is checked — and stays out of the graph
type: decision
updated: '2026-09-11'
---

A body cites another document two ways. `related:` frontmatter is the typed, authored edge:
validated on write, reported by `dangling`, drawn on the graph. `[[...]]` written mid-sentence
was the other one, and nothing in docir had ever read it — not the renderer, not a check, not
the index. It published as literal brackets, and a retitle broke every inbound one in silence.

## The decision

Resolve `[[...]]` against the corpus, render the resolved ones as links, report the unresolved
ones from `docir check` as `unresolved-link`, a **warning**. Do not feed them to the graph.

The rule lives in `platform.naming.links`, beside the tag-key and document-id grammars and for
the same reason (adr-289e788719a7): `documents` reports the broken ones and `publishing` renders
the working ones, neither may import the other, and a rule written twice is how a link comes to
resolve for the renderer and dangle for the check.

## What a target may be

Four forms, because all four are what people write: the document id, the filename stem, the
title slug, and the title itself. A `.md` suffix and a leading directory are stripped, since
both are what a path looks like when pasted. `[[target#heading]]` and `[[target|label]]` parse.

The stem is the form that cannot be derived. `update --set-title` keeps the original filename,
so a retitled document's stem is the slug of a title it no longer has — and the links written
against it are exactly the ones that must keep working. So the stem is carried as data, from
the `path` the `docir get` payload already contains.

## Resolution reads every document

Inactive and archived included. A link to a resolved issue or a superseded decision is a
*working* link — following a decision to the one that replaced it is the point of publishing
the graph — so "not in the default `query`" is never a reason to call one broken.

That was the reporter's own mistake, twice, in the four hand-written passes that produced the
issue: pass two called ten links broken, and the last one that survived was exact and pointed
at a `resolved` document. Anyone validating these outside docir reimplements this rule and gets
it wrong the same way, which is the argument for it being here rather than in a consumer.

## Ambiguity is not resolution

Two documents can share a title, so a title slug can name both. Neither renderer nor check
guesses: the link stays text and the finding lists the candidates. Picking one silently is how
a reader lands on the wrong document with no way to tell.

## Why this is Tier 1 when `unresolved-mention` is not

They look like the same check and are not. An id *named* in a sentence is a citation — writing
`adr-0007` while explaining the id format is correct usage, and measured on this corpus all 47
unresolved mentions were exactly that, so a Tier 1 warning would fire only on documents doing
their job (adr-e86c5040d626). `[[...]]` is not a citation. It is link syntax with no second
reading: whoever typed the brackets meant to point at a document.

The one false positive available is a body demonstrating the syntax, and `scan_wikilinks` skips
code spans and fences. That filter is free here and was not free there: 56 *resolved* mentions
in this corpus live only inside code spans, so filtering them would have deleted 12% of the
working mention graph, while a `[[...]]` inside code was never a link — the renderer works from
the markdown token stream, where a code span is opaque. This repository's only two occurrences
are both inside code spans, in the document explaining what a wikilink is; read literally they
would be the check's two findings, on the document doing its job.

## A warning, not an error

`dangling` is an error because a `related:` edge is a declared, typed claim the write path
validated, so one that resolves to nothing means the corpus was damaged after the fact. A prose
link carries no kind, gates no merge and feeds no graph, so a broken one costs a reader a click.
Promoting it would red-build a repository whose documents are all intact — the failure every
warning in `arch-ad342aae8293` is there to avoid.

`check --fix` leaves it for the same reason it leaves `unknown-type`: a target that resolves to
nothing needs somebody to say which document was meant. The near-miss this was built from is a
slug guessed one word short of the title, which no rule can distinguish from a link to a
document not written yet.

## It stays out of the graph

`orphan` reads `related:` alone, and a `[[...]]` does not clear it — the rule adr-e98749aa457d
settled for mentions, for the same reason. A judgement about a queue must not be cleared by the
prose that triages the queue, and prose that names an orphan is usually the triage of it.

Making prose links structural was the open question in the report and is deliberately not
answered here: `related:` remains the typed layer, and this is navigation.

## What the site renders

The target's **current title**, not the written target. A slug goes stale the day somebody
retitles the document, which is the failure that made these worth resolving, so rendering the
title is the difference between a link that ages and one that does not. `|label` wins where it
is given. A target the site does not publish — an archived document under the default `build` —
stays the literal `[[...]]`, which is what a dangling edge does on the same page.
