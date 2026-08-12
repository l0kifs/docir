---
code:
- src/docir/modules/publishing/infra/diagrams.py
created: '2026-08-12'
description: Why docir build renders mermaid fences as diagrams, and why the runtime
  is a build input like --logo rather than a vendored asset.
id: adr-9c7c1ab8acef
related:
- kind: refines
  to: adr-a343140d72e2
status: accepted
tags:
- architecture
- cli
- docs
title: Mermaid diagrams draw from a supplied runtime, not a bundled one
type: decision
updated: '2026-08-12'
---

## Context

`docir build` publishes every code fence as a titled, syntax-coloured frame
(adr-a343140d72e2). A `mermaid` fence is the one fence where that is wrong: the
author wrote a description of a picture, and every markdown viewer the reader
already uses — GitHub, the IDE preview, the artifact — draws it. Published as
text, the sequence diagram in an architecture note is a wall of arrows the
reader has to compile in their head.

Drawing it needs mermaid's runtime, and that is the whole decision. The bundle
is ~3 MB of JavaScript. Three options were on the table:

1. **Vendor it in the package.** Every install, every CI image and every wheel
   carries it, including the majority of corpora that draw nothing. It also
   puts a minified third-party bundle in docir's supply chain, to be reviewed
   and re-vendored on every mermaid release.
2. **Load it from a CDN.** One line, and it breaks the property the module is
   built around: a published site opens from `file://` and from a host with no
   CDN reachable. A page that silently shows nothing offline is worse than one
   that shows source.
3. **Take it as a build input**, the way `--logo` takes the publisher's mark.

## Decision

Option 3. `docir build --mermaid path/to/mermaid.min.js` supplies the bundle;
docir writes it into the output directory as `mermaid.min.js` and loads it from
there with a **relative classic `<script>`**.

- **Classic, not a module.** A `type="module"` script is fetched under CORS
  rules that `file://` fails, so the site would draw over HTTP and show source
  when opened from disk — the one place it is most likely to be opened. This is
  also why `--mermaid` expects the browser (UMD) build.
- **Written only when a document drew something**, and loaded only on the pages
  that have a diagram. `render_site` knows both, because it is the layer that
  rendered the bodies; nothing else can.
- **Absent runtime degrades to the source.** The element holds its own mermaid
  as preformatted text, framed and copyable. Nothing is hidden behind a script
  that did not load, and no page is worse than the code block it replaced. The
  fallback is also why the source lives in the element's text rather than a
  `data-` attribute: the unrendered state *is* the source, so there is one copy,
  and the bootstrap captures it in JavaScript before the first draw.
- **Diagrams redraw on a theme change.** Mermaid bakes its palette into the SVG
  at `initialize` time, so a diagram drawn in light mode stays light after the
  reader flips the toggle — dark ink on a dark panel. The resolved theme is
  compared against the last one drawn, so the observer's own notification at
  load does not draw twice.
- **The copy button carries the source in `data-copy`** rather than reading a
  sibling `<pre>` as the code-block button does: once drawn, the element holds an
  `<svg>`, and a button that copied what it found would hand back serialized
  markup instead of the mermaid the reader wanted to reuse.
- **`*.js` joins the output sweep.** The site is regenerated wholesale; a runtime
  left behind after the build stopped being given one is an orphan exactly like
  a deleted document's page.

## Consequences

- Diagrams are opt-in, and the opt-in has a real cost: the publisher has to
  source a 3 MB file. Adoption will be low, and that is the trade — the
  alternative charges every install for it.
- Nothing in the suite executes the bootstrap; the project has no JavaScript
  test harness, and `_SHELL_JS` and `_FILTER_JS` are in the same position. The
  rendering, the wiring and the validation are covered
  (`tests/modules/publishing/test_diagrams.py`); the drawing is not.
- If the trade is ever revisited, the shape that changes is only where the
  bundle comes from — the fence rendering, the fallback and the theme redraw are
  independent of it.
