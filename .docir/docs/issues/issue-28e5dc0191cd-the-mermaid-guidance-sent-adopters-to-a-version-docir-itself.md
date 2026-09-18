---
code:
- src/docir/modules/agents/infra/templates/**
- README.md
- src/docir/modules/publishing/infra/diagrams.py
- src/docir/entry_points/cli/app.py
- .github/workflows/pages.yml
code_baseline:
  .github/workflows/pages.yml: 268ada90f0a2
  README.md: 61935297d547
  src/docir/entry_points/cli/app.py: 632b4c81a902
  src/docir/modules/agents/infra/templates/**: 589d2f0899a0
  src/docir/modules/publishing/infra/diagrams.py: 82acf633af1c
created: '2026-08-25'
description: skill and README named mermaid 10.9.3 on the false grounds that 11 is
  ESM-only, while docir's own pages.yml published with 11.16.1.
id: issue-28e5dc0191cd
owner: maintainer
related:
- adr-9c7c1ab8acef
status: resolved
tags:
- cli
- docs
title: The mermaid guidance sent adopters to a version docir itself stopped using
type: issue
updated: '2026-09-18'
---

## What was wrong

The skill and the README told adopters to fetch **mermaid 10.9.3**, on the stated
grounds that "mermaid 11 ships only ES modules" and "10.x is the last line that
has" a browser bundle.

docir's own `pages.yml` has been fetching **11.16.1** and publishing with it.
Nobody noticed the contradiction because both sides are green: the site builds,
and the guidance is prose nothing executes.

The claim is false. mermaid 11's package `exports` do name only
`dist/mermaid.core.mjs`, which is what makes it *look* ESM-only — but
`dist/mermaid.min.js` is still published, and it is a classic script whose last
line is `globalThis["mermaid"] = ...`. docir loads the runtime with a plain
`<script src>`, so that file is exactly what it needs.

## How it was verified

Not by reading the bundle's first line, which only shows it is not an ES module.
The site was built locally against 11.16.1, served over HTTP and opened in a real
browser: one `.docir-mermaid` node, `data-processed` set, one SVG at 554x369 with
194 child elements. That is the difference between "the runtime loaded" and "the
diagram drew".

## The fix

Both surfaces now name `dist/mermaid.min.js` at 11.16.1 and describe the property
that actually matters — the file sets `window.mermaid`, and the `.mjs` entry is
refused. "UMD" is dropped from the skill and the README: mermaid 11's bundle is a plain
IIFE assigning a global, not a Universal Module Definition, and the operative
requirement was never UMD but *classic script*. It survived in two surfaces an
agent also reads — `docir build --help` and the `.mjs` refusal message in
`publishing/infra/diagrams.py` — which kept sending adopters to 10.9.3 on the
disproved "ESM-only" grounds, while the skill's `reference/publishing.md`
described the refusal as carrying the 11.16.1 URL. Those were fixed afterwards,
in the change that made the URL one constant (`diagrams.MERMAID_RUNTIME_URL`).

adr-9c7c1ab8acef is left alone. Its decision — classic and not a module, because
`type="module"` is fetched under CORS rules `file://` fails — is correct and is
the reason this works at all.

## What is still weak

`pages.yml` now opens the built pages in a real browser
(`scripts/assert_diagrams_render.py`, playwright and chromium) and asserts an `<svg>`
with content inside every diagram node; a no-op global and an ESM-only module both
fail it, where the earlier file-exists check passed both. The five guidance surfaces
— the `build` docstring, the refusal, the packaged `reference/publishing.md`,
`README.md` and `pages.yml` — are now held to one version and to no "UMD" by
`test_the_mermaid_guidance_agrees.py`.

What that guard does not read is this store. adr-9c7c1ab8acef went on calling the
runtime the "(UMD) build" after the word was dropped everywhere else, and nothing
would have reported it: the documents describing a surface are not the surface.
