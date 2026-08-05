---
created: '2026-08-04'
description: Why docir build emits graph.html — a deterministic per-type constellation
  map of the corpus — plus a landing-page index, and why the graph is a domain projection
  (graph_payload) rather than a second data path.
id: adr-307ba1f1a820
related:
- kind: refines
  to: adr-a343140d72e2
status: accepted
tags:
- architecture
- cli
- docs
title: The site publishes the relation graph as an interactive constellation page
type: decision
updated: '2026-08-05'
---

## Context
`docir build` (adr-a343140d72e2) publishes one page per document plus an index. The
typed relation graph — the thing that distinguishes docir from a folder of
markdown — was only visible one document at a time, as "links to / linked
from" lists. Three interactive prototypes (constellation, orbit, lanes) were
built against docir's own corpus (105 documents, 166 edges, 69% resolved
issues, 90% `relates_to`); the constellation was selected: overview first, a
deterministic per-type ring layout, filter chips, and a pinned detail card.

## Decision
The build emits **`graph.html`** on every run, linked from the index (a
call-to-action) and from every document page. The index doubles as a landing
page: corpus stats and the graph CTA above the fold, an autofocused filter,
and a "recently updated" strip (skipped for small corpora, hidden while
filtering).

- **The graph is a domain projection.** `graph_payload(site)` derives nodes
  and typed edges from the *resolved* site, so degree counts both directions
  and dangling edges are excluded. The page embeds that JSON; it is exported
  from `api.py` for anything else that wants the same shape.
- **Deterministic layout, no physics.** One ring per type, radius from
  member count, the highest-edge-weight type at the centre, golden-angle
  spirals inside each ring. The same corpus always draws the same map.
- **Closed work is hidden by default.** The site receives no schema, so
  inactive statuses are recognised by name (the union of the bundled
  profiles' inactive statuses); unknown statuses count as open. Unknown
  types and relation kinds get deterministic spare hues rather than a shared
  grey or the `relates_to` fallback style.
- **One chrome, own palettes.** The page shares the site's CSS tokens
  (extracted to `infra/theme.py`); only the type/kind colour vocabularies are
  its own, because the map is where colour carries category.
- **Inline data is script-safe.** `</` is escaped in the embedded JSON so a
  document title cannot terminate the `<script>` element.

## Consequences

- Page count per build grows by one; the graph inlines the corpus skeleton
  (no bodies), so size scales with metadata only.
- The `concepts/` prototype directory is deleted entirely; the module copy is
  canonical, and the three-way comparison (constellation / orbit / lanes)
  survives in this ADR's context section.
- The card's "open document" link hands off from exploration (graph) to
  reading (page); in-card links navigate the graph and relax filters when
  they target a hidden document, so the card and the map cannot disagree.

## Amendments (2026-08-04)

Two follow-on decisions landed the same day, both index/graph UX:

- **Deep links by fragment.** `graph.html#<id>` pins that document on load
  (card open, filters relaxed if they hid it); every document page links to
  it, and pinning keeps the fragment in sync via `replaceState`. A
  `hashchange` listener covers same-document fragment navigation, which
  never re-runs load-time init.
- **Faceted index filters.** Type and status are multi-select checkbox
  facets (OR within, AND across, live result counts); the status facet is
  narrowed by the type selection and drops selections that become
  unavailable. Dates offer rolling presets (7/30/90 days, this year) plus an
  absolute custom range — rolling for "what changed lately" links,
  absolute for citations. The whole state mirrors into the URL query.
  Chosen over single-selects after the standard faceted-search findings
  (counts per option, dependent facets, instant application).
- **`[hidden]` reset.** Author `display` rules on rows and facet labels
  overrode the UA's `[hidden]` mapping, so filtered-out rows never left
  the screen when their section stayed visible. Both stylesheets now carry
  `[hidden]{display:none!important}`.
