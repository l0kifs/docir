---
created: '2026-08-15'
description: 'How docir build renders the corpus for the people who approve decisions:
  the flags, publishing from CI, the --out guard, and mermaid diagrams.'
id: run-6ab65e277573
owner: maintainer
related:
- adr-a343140d72e2
- adr-9c7c1ab8acef
- adr-307ba1f1a820
status: active
tags:
- docs
- cli
title: Publish the store as a static site
type: runbook
updated: '2026-08-15'
---

An agent reads docir through the CLI or MCP. The people who have to *approve* a
decision usually are not at a terminal, and a decision only an agent can read is a
hard sell to them. `docir build` renders the whole store as a static site — one page
per document, plus an index.

## The command

```bash
docir build --out site/                                    # every active document
docir build --out site/ --title "Acme — decisions"         # heading, browser tab, wordmark
docir build --out site/ --logo brand/mark.svg              # your mark in the corner and the tab
docir build --out site/ --mermaid vendor/mermaid.min.js    # draw ```mermaid fences as diagrams
docir build --out site/ --include-archived                 # publish archived documents too
```

The result is self-contained — inline CSS, no external requests — so it opens from
`file://` and publishes to GitHub Pages or S3 unchanged.

## Always pass `--title`

`--title` is what the site calls itself: the heading, the browser tab and the name
beside the mark. Without it every page reads "Documentation", which tells a reviewer
nothing about whose decisions they are looking at. `--logo` sets the top-left mark
*and* the favicon; without it the site carries docir's own.

## What the site shows that a file listing cannot

It publishes what only docir knows:

- the typed relation graph **in both directions** — a superseded decision says so, in
  a banner, linking the document that replaced it;
- the staleness flag, so a reviewer can see nobody has vouched for a page within its
  cadence;
- tags, owner and dates, as metadata rather than prose.

Archived documents are left out unless you ask for them.

## Publishing from CI

docir publishes its own store this way, from
[`.github/workflows/pages.yml`](https://github.com/l0kifs/docir/blob/main/.github/workflows/pages.yml).
Copy that workflow, then enable Pages once under Settings → Pages → Source:
**GitHub Actions**.

**Reindex first.** `.docir/docs/` is committed and the index is gitignored, so a fresh
clone has no index at all, and `build` reads the index rather than the files. Without
the reindex step the job publishes a site with an empty document list and exits 0. It
warns on stderr, and the workflow gates on the page count — but the reindex is what
makes the point moot.

## `--out` is regenerated, which is why it is guarded

Every build removes the pages it finds before writing new ones: a document deleted
from the store must not survive as an orphaned page nobody can reach and nobody knows
is stale. "Delete everything here first" has to be sure it owns "here", so a directory
docir did not build is refused unless you pass `--force`. A previous build is
recognised and overwritten without the flag.

## Diagrams draw from a runtime you supply

A fenced `mermaid` block is the one code block whose author meant the picture, so the
site draws it — given a runtime. Mermaid's browser bundle is megabytes of JavaScript,
which docir will not put in every wheel to serve the corpora that draw diagrams, so
you supply it: `--mermaid path/to/mermaid.min.js` writes it beside the pages and loads
it from there. No CDN, so the site still opens from `file://`; it is written only when
some document actually draws something, and loaded only on the pages that do.

Without the flag the diagram publishes as its own source, framed and copyable — the
same block you have today.

## Build is single-store

`build` does not federate. A published site is one store's corpus: a copy of a peer's
decision would age the moment that repo edits it, and that repo publishes its own site.
