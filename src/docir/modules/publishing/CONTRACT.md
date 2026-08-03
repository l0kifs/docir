# publishing

## Purpose
Renders a docir corpus into a **self-contained static site** — one HTML page per
document plus an index — so the people who approve a decision can read it without
a terminal. Log4brains publishes ADRs this way; docir additionally publishes the
typed relation graph and staleness, which no other ADR site shows.

## Public operations
- `build_site_builder() -> SiteBuilder` — wire the builder
- `SiteBuilder.build(PublishRequest) -> PublishResult` — render and write the site
- `build_site(views) -> Site` — resolve payloads into the site model without
  rendering or writing (used by tests and by anything that wants the graph)

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
  inlined; there are no external requests, so a site works from `file://`.
- Text interpolated as text is HTML-escaped; only the document body is rendered
  as markdown.

## Dependencies
`platform.errors` only, plus `markdown-it-py` for body rendering. A leaf module.
