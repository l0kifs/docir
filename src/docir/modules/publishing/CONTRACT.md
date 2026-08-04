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
`docir get` payloads), `title`, `version` and `force`. `PublishResult` reports
`out`, `pages`, `documents`, `stale` and the `files` written.

## Behavioural guarantees
- **Input is data, not services.** `documents` is the documented JSON shape of
  `docir get`; absent keys read as their defaults, so a site can be built from
  captured CLI output. This module imports nothing from `documents`.
- **The output directory is regenerated wholesale** — every `*.html` is removed
  before writing, so a document deleted from the store cannot survive as an
  orphaned page. A directory that is neither empty nor a previous docir site
  (marked by `.docir-site`) is refused unless `force`.
- **Both edge directions are rendered.** Outgoing edges come from frontmatter;
  incoming edges are inverted from every other document, because a page has to
  show what points at it. `supersedes`/`contradicts` inbound edges are surfaced
  as a banner, not buried in a list.
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
- **The index is a landing page**: corpus stats and the graph call-to-action
  above the fold, an autofocused filter, and a "recently updated" strip that
  is skipped for small corpora and hidden while any filter is active.
- **Index filters are faceted and shareable.** Type and status are
  multi-select checkbox facets (OR inside a facet, AND across facets and the
  free-text query) with live result counts; options are derived from the
  corpus. The status facet is narrowed to the statuses the selected types can
  have, and a selection that becomes unavailable is dropped. The date facet
  filters on `updated` with rolling presets (7/30/90 days, this year) plus an
  absolute custom from/to range. The combined state is mirrored into the URL
  query (`?type=a,b&status=x,y&updated=30d` or `&from=…&to=…`, plus `q=`),
  so a filtered view is a copyable link that restores on load; unknown query
  values are dropped rather than filtering to zero.
- Text interpolated as text is HTML-escaped; only the document body is rendered
  as markdown.

## Dependencies
`platform.errors` only, plus `markdown-it-py` for body rendering. A leaf module.
