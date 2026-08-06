---
code:
- src/docir/modules/publishing/**
created: '2026-08-03'
description: Why docir build renders a static site, and why the module takes JSON
  rather than a DocumentService.
id: adr-a343140d72e2
owner: maintainer
related:
- kind: refines
  to: arch-322e5f992ad2
- ref-a6db21f52427
- adr-3a2d5ee7bc84
status: accepted
tags:
- architecture
- cli
- docs
title: A publishing module that takes documents as data
type: decision
updated: '2026-08-06'
---

## Context
docir was CLI-only. That quietly assumed the people who must *approve* a
decision are the people who run commands, and they are not: a PR reviewer, a
new hire and a manager all read decisions, and none of them will type
`docir get adr-3f9a2b1c7d4e`. Log4brains' entire pitch is publishing ADRs as a
browsable site, and the competitor survey (`ref-a6db21f52427`) listed this as
gap 5 — the one that changes *who docir is for* rather than how well it ranks.

Two shapes were considered. A `docir serve` browser UI over the live store is
better for exploration but leaves no artifact: nothing to link in a pull
request, nothing CI can publish, a process to run. A static site is a derived,
throwaway projection of the canonical files — which is the architecture's own
first thesis, applied to a second output.

The harder question was where the code goes. `publishing` needs documents, and
the module rules allow a module to import only another module's `api`. Adding
`publishing -> documents.api` would be a new cross-module edge in a graph whose
only permitted ones are `tags -> documents -> indexing`.

## Decision
A new **leaf module `publishing`** that takes documents as **data**, not as a
service. Its input is a sequence of mappings in the shape `docir get` returns;
it imports nothing but `platform.errors` (and `markdown-it-py` for body
rendering, in `infra`). The entry point fetches and hands over.

That resolves the boundary question by making it moot, and it is better design
independently: rendering has no business knowing what a repository is. The site
becomes a projection of docir's **public contract** rather than a second reader
of the aggregate — which also means a site can be built from captured CLI
output, because absent keys read as their defaults exactly as trimmed JSON
promises.

`docir build --out site/` writes one page per document plus a filterable index.

- **Self-contained.** CSS, the filter script and the theme rules are inlined;
  there is not a single external request. A published site must work from
  `file://` and from a host with no CDN reachable, and an asset pipeline for a
  few hundred lines of CSS is a build step to maintain, not a feature. It is
  also a privacy property: a page that fetches a font tells someone else who is
  reading your architecture decisions.
- **Both edge directions are rendered, and that is the differentiator.**
  Outgoing edges come from frontmatter. Incoming edges are inverted from every
  other document, because a reader landing on an old decision needs to know
  something replaced it — and that edge lives on the *other* document's
  frontmatter. An inbound `supersedes`/`contradicts` becomes a banner above the
  body, not a line in a list, because burying it is the failure the typed graph
  exists to prevent. No other ADR site shows this.
- **A dangling edge stays visible** as a bare id, so the site reports the same
  broken reference `docir check` does rather than hiding a defect behind a
  missing row.
- **The output directory is regenerated wholesale**, which is what forces the
  guard. A document deleted from the store must not survive as an orphaned page
  nobody can reach and nobody knows is stale — the web equivalent of an index
  row whose file is gone. "Delete every `*.html` here first" has to be sure it
  owns "here": a previous build leaves a `.docir-site` marker, and anything else
  non-empty is refused unless `--force`, because `--out` is a path a person
  types and a typo pointing at `src/` should not be answered by writing HTML
  into it.
- **Inactive documents are published; archived ones are not.** Hiding closed
  documents is right for `context`, which is a working set, and wrong for a
  browsable corpus, where a superseded decision is exactly what someone arrives
  at from an old link and where the successor banner is the answer.
- **The build does one `query` then one `get` per document.** Bodies are absent
  from every list path by contract, so this is N+1 requests — the right trade
  for an occasional offline operation against widening a read path that exists
  to stay narrow.

## Consequences
- **docir has a second audience.** Everything up to here — MCP, chunking,
  `get --section` — made the corpus cheaper for an agent. This makes it legible
  to a human who will never install docir.
- **The N+1 is real and bounded.** 104 documents build in about a second
  in-process; over the daemon it is 105 socket round trips. If a corpus ever
  makes that hurt, the fix is a dispatcher `export` command, not a body on
  `query`.
- **A build that stopped at `query` would look exactly like success** — right
  document count, right page count, empty bodies. That failure mode is pinned
  by a test rather than left to review.
- **Two more declared dependencies, both already present.** `markdown-it-py`
  arrived with Rich and `watchfiles` with fastmcp; depending on someone else's
  transitive dependency is depending on their next release notes.
- **No templating engine.** The HTML is f-strings in `infra/rendering.py`. That
  is a deliberate ceiling: this renders one document type in one layout, and
  Jinja2 would buy flexibility nobody has asked for at the cost of a dependency
  and a template directory. Revisit when a second layout exists, not before.
- **CSS is now a maintenance surface docir has never had.** It is one inline
  block with a light and a dark palette, and it should stay that size.
