# publishing

## Purpose
Renders a docir corpus into a **self-contained static site** — one HTML page per
document, an index that works as a landing page, and an interactive **graph
page** drawing the typed relation graph as a per-type constellation map — so
the people who approve a decision can read it without a terminal. Log4brains
publishes ADRs this way; docir additionally publishes the typed relation graph
and staleness, which no other ADR site shows.

## Public operations
- `build_site_builder() -> SiteBuilder` — wire the builder
- `SiteBuilder.build(PublishRequest) -> PublishResult` — render and write the site
- `build_site(views) -> Site` — resolve payloads into the site model without
  rendering or writing (used by tests and by anything that wants the graph)
- `graph_payload(site) -> {nodes, edges}` — the resolved relation graph as
  data: per-node type/status/tags/degree plus typed edges, dangling targets
  excluded. What the graph page embeds; exported for anything else that wants
  the same projection.

`PublishRequest` carries `out` (target directory), `documents` (a sequence of
`docir get` payloads), `title`, `version`, `logo` (an optional path to the
publisher's own mark), `mermaid` (an optional path to mermaid's browser bundle)
and `force`. `PublishResult` reports `out`, `pages`, `documents`, `stale` and
the `files` written.

## Behavioural guarantees
- **Input is data, not services.** `documents` is the documented JSON shape of
  `docir get`; absent keys read as their defaults, so a site can be built from
  captured CLI output. This module imports nothing from `documents`.
- **A site is one store's corpus.** Reads federate across declared peers
  (adr-fb938175f72a) and `build` is assembled from `query` + `get`, so the
  caller opts the pair out explicitly; this module is handed the local corpus
  and nothing else. Publishing a peer's document here would make a copy that
  goes stale the moment that repository edits it — the failure the staleness
  model exists to prevent — while claiming, in the same summary line, to be
  this store's site. A peer publishes its own.
- **The output directory is regenerated wholesale** — every `*.html` and
  `*.md` is removed before writing, so a document deleted from the store
  cannot survive as an orphaned page or an orphaned source. A directory that
  is neither empty nor a previous docir site (marked by `.docir-site`) is
  refused unless `force`.
- **Each document publishes twice: a page and its markdown.** `<id>.html` is
  the rendered page and `<id>.md` is the body verbatim, linked from the page
  as "View as Markdown" — a reader who wants to quote or diff a document
  should not have to install docir to reach its source. Only the body: the
  frontmatter is index input, and the page already renders every field of it.
- **The logo is a build input, and it brands the corner and the tab
  together.** `logo` publishes the publisher's own (svg/png/jpg/webp/gif,
  capped at 64 KiB) as both the top-bar mark and the favicon; absent, the site
  carries docir's. One flag, because a page whose corner says Acme and whose
  tab says docir is half-applied branding. Everything is inlined into every
  page — docir's mark as SVG using `currentColor`, so the kit's ink and paper
  marks collapse into one that is right in both themes with the caret's signal
  amber fixed; docir's favicon as the *opaque tile*, which is what stays
  legible on dark browser chrome, drawn from the same two path strings as the
  mark so the pair cannot drift; a supplied logo as a `data:` URI inside
  `<img>`, which renders it and lets it do nothing else. The logo is resolved
  before any file is removed, so a bad path fails the build instead of
  emptying the output directory first.
- **The graph page wears the same chrome as the pages.** The same 56px top bar
  in the same order — mark and title left, then the search box, the view's own
  toggles, the way back, and the three-state theme control — the same panel
  treatment on its legend and detail card, and the same relation vocabulary:
  the card groups edges by kind with the direction in the label, exactly as a
  document's rail does, from one `INBOUND_KIND` map in the domain so the two
  cannot disagree. It is one page of a site, not a second tool wearing the
  same colours.
- **Every page shares one shell.** A sticky top bar (search, review-queue link
  when anything is stale, graph link, theme toggle), a sidebar listing the
  whole corpus grouped by type with the current document marked, and — on
  document pages — a rail carrying, in this order, the contents, a trust panel
  (owner/verified/created/updated; no cadence or due date is invented — the
  site receives no schema, and the staleness flag is the derived signal), the
  local 1-hop relation map, and the relation lists. The rail precedes the body
  in source order, preserving the nothing-important-below-the-fold guarantee
  without CSS. A ⌘K palette searches client-side over the sidebar's own links
  and offers the site's actions (all documents, the graph, the review queue
  when anything is stale, the theme) — one copy of the corpus per page, no
  fetch. The theme is three-state (auto/light/dark), persisted in
  `localStorage` and restored before first paint.
- **Code blocks are framed, titled and coloured.** Each carries its language
  and a copy button in a header outside the `<pre>`, and a five-role syntax
  theme (comment / keyword / string / function / flag) covering shell, python,
  yaml, json, sql and toml. An unrecognised language renders plain rather than
  guessing — a wrong colour asserts a structure the source does not have.
- **A `mermaid` fence is a picture, and its runtime is a build input.** The one
  fence whose author meant the diagram rather than the text renders as a figure
  wearing the code block's frame. `mermaid` supplies mermaid's browser bundle;
  it is written beside the pages as `mermaid.min.js` and loaded from there with
  a relative classic `<script>` — never a CDN, and never a module, because both
  break a site opened from `file://`. It is written **only when some document
  actually drew a diagram**, and loaded only on the pages that have one: the
  bundle is megabytes. Without it the element holds its own source as
  preformatted text, framed and copyable — a page whose runtime is absent is no
  worse than the code block it replaced. Diagrams are redrawn on a theme change,
  because mermaid bakes its palette into the SVG at render time.
- **Chrome identifies a document only by its docir id.** The breadcrumb leaf,
  the id chip and the copyable `docir get <id>` command all carry the id;
  sequence labels inside titles ("adr-a343140d72e2") are title text, never parsed or
  displayed as identity. Every page ends with the copyable
  `docir update <id>` / `--verified` commands: the site is read-only and says
  what the write path is.
- **The reader never has to click to find out what a link is.** A relation
  link carries its target's title, description and metadata, shown as a hover
  preview; the relation lists are open, not folded behind their own count;
  the landing page carries corpus stat tiles (documents / types / resolved
  relations / stale, the last one linking into the review queue) once the
  corpus is large enough to browse. The corpus size is stated once: the tiles
  replace the sub-line rather than repeating it.
- **Statuses are coloured by name, neutrally when unknown.** The bundled
  vocabularies map to good/warning/bad/done chip colours; an unrecognised
  status renders as the neutral chip rather than guessing a meaning.
- **Both edge directions are rendered.** Outgoing edges come from frontmatter;
  incoming edges are inverted from every other document, because a page has to
  show what points at it. Relation panels group their edges by kind.
  `supersedes`/`contradicts` inbound edges are surfaced as a banner, not
  buried in a list, and come first in the local map. Document pages carry
  previous/next within their type, in the listing's order.
- **A dangling edge stays visible** as a bare id, so the site shows the same
  broken reference `docir check` reports.
- **Pages are offline-complete.** CSS, the filter script and the theme rules are
  inlined; there are no external requests, so a site works from `file://`. The
  graph page inlines its data the same way and additionally escapes `</` in the
  embedded JSON, so a document title cannot terminate the script element.
- **The graph deep-links by fragment.** `graph.html#<id>` loads with that
  document pinned (its card open, filters relaxed if they hid it), and every
  document page links to `graph.html#<its id>`; pinning keeps the fragment in
  sync, so the current selection is always shareable. An unknown fragment
  lands on the plain overview.
- **The graph page hides closed work by default** (a "show closed" toggle
  reveals it). The site receives no schema, so inactive statuses are recognised
  by name — the union of the bundled profiles' inactive statuses; an unknown
  status counts as open. Types and relation kinds outside the built-in palettes
  get deterministic spare hues rather than a shared grey.
- **The index is a landing page**: corpus stat tiles above the fold, an
  autofocused filter, and a "recently updated" strip that is skipped for small
  corpora and hidden while any filter is active. Listing rows are two lines
  and a gutter — title, description, then state/status chips and the updated
  date — with tags searchable through the row's haystack rather than printed
  under every row. The graph is reached from the top bar, which is on every
  page rather than the landing alone.
- **Index filters are faceted, chip-displayed and shareable.** Type, status
  and — when any document has one — owner are multi-select checkbox facets
  (OR inside a facet, AND across facets and the free-text query) with live
  result counts; options are derived from the corpus. Every applied filter is
  a removable chip above the list — the canonical display of state. The text
  box doubles as a token bar: `type:x`, `status:x`, `owner:x`, `is:stale`,
  `updated:30d` and their `-` negations convert to chips when the value
  exists in the corpus; anything else stays free text. A stale toggle renders
  when the corpus has stale documents, and the stale tile, the rail's review
  note and the top bar's queue link all point at the same state (`?is=stale`).
  An option whose count under the other filters is zero
  dims and disables rather than disappearing, and a selection is never
  silently dropped — its chip stays visible as the cause of an empty list. A
  zero-result list offers "remove last filter" and "clear all" instead of
  dead-ending. The date facet filters on `updated` with rolling presets
  (7/30/90 days, this year) plus an absolute custom from/to range. Corpora
  large enough for the recent strip also get one-click preset views (all /
  stale / open issues / updated·7d), each equal to a filter state. The
  combined state is mirrored into the URL query
  (`?type=a,-b&status=x&owner=o&is=stale&updated=30d` or `&from=…&to=…`,
  plus `q=`), so a filtered view is a copyable link that restores on load;
  unknown values are dropped rather than filtering to zero. Each facet change
  is a history entry, so Back undoes filter steps; typing only replaces.
- Text interpolated as text is HTML-escaped; only the document body is rendered
  as markdown.

## Dependencies
`platform.errors` only, plus `markdown-it-py` for body rendering. A leaf module.
