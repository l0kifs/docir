---
code:
- src/docir/modules/publishing/infra/rendering.py
created: '2026-09-11'
description: 'The one audited smell still untreated: 2,072 lines over CSS, the index
  page, the document page, the chips and the markdown pipeline.'
id: issue-55cc9295302a
owner: maintainer
related:
- adr-a343140d72e2
- kind: refines
  to: adr-a1754eb79fe7
status: open
tags:
- architecture
- cosmetic
title: publishing/infra/rendering.py changes for three unrelated reasons
type: issue
updated: '2026-09-11'
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
