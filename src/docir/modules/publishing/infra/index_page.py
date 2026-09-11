"""The corpus index: the rail, the facet filters, the tiles and the recent list.

**The index is a grid list, not a table**, and the difference was measured in a
browser. A four-column table came to 426px at a 390px viewport — the page
scrolled sideways — and one row was 388px tall, so a 105-document index showed
two rows per screen. A grid reflows to one column.
"""

from __future__ import annotations

import html
from collections.abc import Iterable

from docir.modules.publishing.domain.site import Site, SiteDocument
from docir.modules.publishing.infra.assets import FILTER_JS
from docir.modules.publishing.infra.branding import Branding
from docir.modules.publishing.infra.chips import state_chips, status_chip, type_dot, type_label
from docir.modules.publishing.infra.page_shell import page_name, render_page, render_sidebar

#: How many documents the "recently updated" strip shows. Below roughly twice
#: this, the strip would just repeat the listing underneath it.
_RECENT_COUNT = 5


def render_index(site: Site, *, title: str, version: str, branding: Branding) -> str:
    """The landing page, shaped by the usual landing rules, not invented ones.

    Everything a first-time visitor needs sits above the fold: the headline
    names the corpus, the stat tiles carry its health at a glance (documents,
    types, relations, stale — the last one the review queue's front door), and
    the filter is the first focusable thing on the page. A "recently updated"
    strip surfaces freshness before the full type listing, because the reader
    who visits twice wants what changed, not the taxonomy.

    The stats appear once. They used to run as a sub-line under the headline
    *and* as tiles directly below it, so a large corpus stated its own size
    twice in two typefaces; the sub-line now renders only for a corpus too
    small for tiles. The graph is reached from the top bar, which is on every
    page — a landing-only call-to-action was the one exit a reader arriving
    on a document could not see.
    """
    sections = "\n".join(_render_group(name, documents) for name, documents in site.groups)
    tiles = _render_tiles(site)
    total = len(site.documents)
    stats = f"{total} document{'s' if total != 1 else ''}"
    if site.groups:
        stats += f" · {len(site.groups)} type{'s' if len(site.groups) != 1 else ''}"
    if site.stale_count:
        stats += f" · {site.stale_count} stale"
    subline = "" if tiles else f'<p class="standfirst">{stats}</p>'
    body = f"""\
<header class="top">
  <h1>{html.escape(title)}</h1>
  {subline}
</header>
{tiles}
<input id="q" type="search"
       placeholder="Filter… try type:decision, is:stale, -status:superseded \
 (/ to focus, ⌘K to search)"
       aria-label="Filter documents" autocomplete="off" autofocus>
{_render_filter_bar(site)}
{_render_views(site)}
{_render_recent(site)}
{sections}
<div class="norec" id="noHits" hidden>
  <p>No documents match this combination.</p>
  <button id="undoLast">Remove last filter</button>
  <button id="clearAllBtn">Clear all filters</button>
</div>
<script>{FILTER_JS}</script>"""
    return render_page(
        title,
        body,
        version,
        site_title=title,
        sidebar=render_sidebar(site, active="index"),
        branding=branding,
        rail=_render_corpus_rail(site),
        stale_count=site.stale_count,
    )


def _render_corpus_rail(site: Site) -> str:
    """The landing's rail: how healthy the corpus is, and what is in it.

    The health rows are the numbers `docir check` reports, which is the point
    — a reader who never runs the CLI still sees whether the corpus is
    maintained. The type legend doubles as the map's key: same dot, same
    colour, same order as the sections below it.
    """
    if not site.documents:
        return ""
    dangling = sum(
        1 for document in site.documents for edge in document.outgoing if edge.title is None
    )
    verified = sum(1 for document in site.documents if document.verified)
    last_updated = max(document.updated for document in site.documents)
    rows = [
        ("Last updated", html.escape(last_updated)),
        ("Verified", f"{verified} of {len(site.documents)}"),
        ("Dangling edges", str(dangling)),
    ]
    health = "".join(
        f'<div class="trow"><span class="k">{key}</span><span class="v">{value}</span></div>'
        for key, value in rows
    )
    if site.stale_count:
        health += (
            f'<div class="trow stale-note"><a href="?is=stale">'
            f"⚠ {site.stale_count} past review →</a></div>"
        )
    legend = "".join(
        f'<li><a href="?type={html.escape(name)}">{type_dot(name)}'
        f"{html.escape(type_label(name, plural=True))}"
        f' <span class="n">· {len(documents)}</span></a></li>'
        for name, documents in site.groups
    )
    return (
        f'<div class="railgrp"><h2>Corpus health</h2><div class="trust">{health}</div></div>'
        f'<div class="railgrp legend"><h2>Types</h2><ul>{legend}</ul></div>'
    )


def _render_filter_bar(site: Site) -> str:
    """Faceted filters beside the free-text one: type, status, owner, updated.

    Facet options are checkboxes (multi-select is OR inside a facet, AND
    across facets) with result counts, derived from the corpus rather than a
    schema the site does not receive — an option no document matches filters
    to an empty page and looks broken. The owner facet renders only when a
    document has an owner; the stale toggle only when something is stale. The
    date facet offers rolling presets plus an absolute custom range. The
    script keeps every count live (a zero-count option dims rather than
    vanishing), displays the applied state as removable chips, and mirrors
    the combined state into the URL query so a filtered view is a copyable
    link — one history entry per facet step, so Back undoes filtering.
    """
    type_counts = [(name, len(documents)) for name, documents in site.groups]
    status_totals: dict[str, int] = {}
    owner_totals: dict[str, int] = {}
    for document in site.documents:
        status_totals[document.status] = status_totals.get(document.status, 0) + 1
        if document.owner:
            owner_totals[document.owner] = owner_totals.get(document.owner, 0) + 1
    presets = [
        ("", "any time", True),
        ("7d", "last 7 days", False),
        ("30d", "last 30 days", False),
        ("90d", "last 90 days", False),
        ("year", "this year", False),
        ("custom", "custom range", False),
    ]
    preset_rows = "".join(
        f'<label><input type="radio" name="dpre" value="{value}"'
        f"{' checked' if checked else ''}>{label}</label>"
        for value, label, checked in presets
    )
    owner_facet = (
        f"""
  <details class="facet">
    <summary>Owner<span id="osum"></span></summary>
    <div class="fopts" id="oopts">{_facet_options(sorted(owner_totals.items()))}</div>
  </details>"""
        if owner_totals
        else ""
    )
    stale_toggle = (
        '\n  <button id="staleTgl" title="past review cadence">⚠ Stale</button>'
        if site.stale_count
        else ""
    )
    return f"""\
<div class="fbar">
  <details class="facet">
    <summary>Type<span id="tsum"></span></summary>
    <div class="fopts" id="topts">{_facet_options(type_counts)}</div>
  </details>
  <details class="facet">
    <summary>Status<span id="ssum"></span></summary>
    <div class="fopts" id="sopts">{_facet_options(sorted(status_totals.items()))}</div>
  </details>{owner_facet}
  <details class="facet">
    <summary>Updated<span id="dsum"></span></summary>
    <div class="fopts">{preset_rows}<div class="drange">
      <label>from <input type="date" id="dfrom"></label>
      <label>to <input type="date" id="dto"></label>
    </div></div>
  </details>{stale_toggle}
  <button id="fclear" hidden>Clear filters</button>
  <span id="fcount"></span>
</div>
<div class="fchips" id="chipsBar" hidden aria-label="applied filters"></div>"""


def _facet_options(counts: list[tuple[str, int]]) -> str:
    return "".join(
        f'<label data-fv="{html.escape(value)}">'
        f'<input type="checkbox" value="{html.escape(value)}">{html.escape(value)}'
        f'<span class="n">{count}</span></label>'
        for value, count in counts
    )


def _render_tiles(site: Site) -> str:
    """Corpus health as stat tiles — the landing's at-a-glance row.

    Rendered at the recent strip's threshold: under it the tiles would
    restate the sub-line twice as loudly. The relation count is resolved
    edges only, matching what the graph draws. The stale tile is the review
    queue's front door.
    """
    if len(site.documents) <= _RECENT_COUNT * 2:
        return ""
    edges = sum(
        1 for document in site.documents for edge in document.outgoing if edge.title is not None
    )
    stale = site.stale_count
    stale_tile = (
        f'<a class="tile linky" href="?is=stale"><span class="v">{stale} stale</span>'
        '<span class="k">review queue →</span></a>'
        if stale
        else '<div class="tile"><span class="v">0</span><span class="k">stale</span></div>'
    )
    return (
        '<div class="tiles">'
        f'<div class="tile"><span class="v">{len(site.documents)}</span>'
        '<span class="k">documents</span></div>'
        f'<div class="tile"><span class="v">{len(site.groups)}</span>'
        '<span class="k">types</span></div>'
        f'<div class="tile"><span class="v">{edges}</span><span class="k">relations</span></div>'
        f"{stale_tile}</div>"
    )


def _render_views(site: Site) -> str:
    """Preset views — one-click filter states, shown only at browsing scale.

    Each button carries its target state as the exact query string the filter
    script serializes, so a preset lights up when the reader assembles the
    same state by hand, and clicking one is just "clear, then apply these
    params". Rendered at the recent strip's own threshold: shortcuts through
    a listing that fits on one screen are furniture.
    """
    if len(site.documents) <= _RECENT_COUNT * 2:
        return ""
    buttons = ['<button data-sig="">All</button>']
    if site.stale_count:
        buttons.append(f'<button data-sig="is=stale">Stale · {site.stale_count}</button>')
    if any(d.type == "issue" and d.status == "open" for d in site.documents):
        buttons.append('<button data-sig="type=issue&amp;status=open">Open issues</button>')
    buttons.append('<button data-sig="updated=7d">Updated · 7 days</button>')
    return f'<div class="views" id="views"><span class="vlbl">Views</span>{"".join(buttons)}</div>'


def _render_recent(site: Site) -> str:
    """The freshness strip — what changed, before the taxonomy.

    Skipped for a small corpus, where the full listing *is* the recent list
    and the strip would duplicate most of it. Items are not filterable
    (no ``data-hay``): while a query is active the script hides the whole
    strip, because every match already appears in its type section.
    """
    if len(site.documents) <= _RECENT_COUNT * 2:
        return ""
    recent = sorted(
        sorted(site.documents, key=lambda d: d.id),
        key=lambda d: d.updated,
        reverse=True,
    )[:_RECENT_COUNT]
    items = "\n".join(_render_item(document, filterable=False) for document in recent)
    return f"""\
<section id="recent">
<h2 class="section">Recently updated</h2>
<ul class="docs">
{items}
</ul>
</section>"""


def _render_group(type_name: str, documents: Iterable[SiteDocument]) -> str:
    documents = tuple(documents)
    items = "\n".join(_render_item(document) for document in documents)
    return f"""\
<section data-type="{html.escape(type_name)}">
<h2 class="section">{type_dot(type_name)}\
{html.escape(type_label(type_name, plural=True))} <span class="n">{len(documents)}</span></h2>
<ul class="docs">
{items}
</ul>
</section>"""


def _render_item(document: SiteDocument, *, filterable: bool = True) -> str:
    # The haystack carries every field the filter searches. Built here rather
    # than in JS so the page filters with the markup alone, no fetch. The
    # recent strip opts out: its rows mirror ones the type sections already
    # carry, and matching both would double-count every hit.
    haystack = " ".join(
        [
            document.id,
            document.title,
            document.description,
            document.status,
            document.type,
            *document.tags,
            document.owner,
        ]
    ).lower()
    hay = (
        f' data-hay="{html.escape(haystack)}"'
        f' data-type="{html.escape(document.type)}"'
        f' data-status="{html.escape(document.status)}"'
        f' data-updated="{html.escape(document.updated)}"'
        if filterable
        else ""
    )
    if filterable and document.owner:
        hay += f' data-owner="{html.escape(document.owner)}"'
    if filterable and document.stale:
        hay += ' data-stale="1"'
    # Two lines and a right-hand gutter. Tags rode under every row as a third
    # line of grey pills — 105 rows of them turned the index into a tag cloud
    # with titles in it, and the same words are still searchable through the
    # haystack and reachable from the document page.
    return f"""\
<li{hay}>
  <div>
    <a class="t" href="{page_name(document.id)}">{html.escape(document.title)}</a>
    <p class="d">{html.escape(document.description)}</p>
  </div>
  <div class="side">{state_chips(document)}{status_chip(document)}\
<time datetime="{html.escape(document.updated)}">{html.escape(document.updated)}</time></div>
</li>"""
