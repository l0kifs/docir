---
code:
- src/docir/modules/publishing/infra/rendering.py
code_baseline:
  src/docir/modules/publishing/infra/rendering.py: 16d9f4392c5b
created: '2026-09-11'
description: 'The one audited smell still untreated: 2,072 lines over CSS, the index
  page, the document page, the chips and the markdown pipeline.'
id: issue-55cc9295302a
owner: maintainer
related:
- kind: refines
  to: adr-a1754eb79fe7
- adr-a343140d72e2
status: resolved
tags:
- architecture
- cosmetic
title: publishing/infra/rendering.py changes for three unrelated reasons
type: issue
updated: '2026-09-22'
verified: '2026-09-22'
verified_code:
  src/docir/modules/publishing/infra/rendering.py: 16d9f4392c5b
verified_content: 3d7f95a53564
---

## Context

A smell audit over `src/docir` named this file as a Divergent Change case and
left it. Everything else both audit passes read and left alone is
[[adr-a1754eb79fe7]] — conclusions rather than work, which is why they are a
decision and this is an issue.

## The finding

`src/docir/modules/publishing/infra/rendering.py` is 2,072 lines over five
concerns — CSS constants, the index page, the document page, the chips, and the
markdown pipeline. Divergent Change is real: the file changes for branding
reasons, for site-structure reasons and for linkify reasons, independently.

It was left because splitting it is a multi-file sweep, not one
behaviour-preserving move, and that is a different kind of change from the six
that shipped. Two things any attempt must respect: the module docstring records
layout decisions measured in a browser rather than reasoned from the markup, and
it has to travel with the code it explains; and the module is a leaf that takes
documents as data, which is what keeps it out of the aggregate.

## What would close this

`rendering.py` stops changing for three unrelated reasons — or a reading of it
concludes the five concerns are one after all, which is an answer worth
recording rather than a failure to act.

Treating it needs a sweep rather than a single behaviour-preserving move, so it
is the one finding here that does not fit the local refactoring loop the rest of
the branch used.

## Resolution

Split into seven modules under `publishing/infra/`, one per reason to change:
`assets` (the inlined CSS and scripts), `chips` (the classification vocabulary),
`page_shell` (the HTML shell and the filenames), `markdown` (the token pipeline
and cross-references), `index_page`, `document_page`, and `rendering` itself —
now 114 lines holding `render_site` and `render_search_index` and nothing else.

Dependencies run one way, `assets <- chips <- page_shell <- markdown`, with the
two page renderers above and `rendering` on top. `publishing` is still a leaf
that takes documents as data.

Behaviour is unchanged and was checked three ways rather than asserted: every
one of the 422 files `docir build` produces from this store is byte-identical
before and after; every function body is AST-identical to its pre-split
counterpart once the renames are normalised; and the suite passes unmodified.

The measured decisions moved with the code they explain — the grid index, the
relation placement, the chip vocabulary, the dropped leading title, the scoped
class names. That was the condition this issue set, and it took two
fresh-context audits to actually meet: the first pass left eleven explanations
stranded in a file whose own docstring claimed they had moved.
