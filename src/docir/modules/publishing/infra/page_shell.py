"""The HTML document every page is poured into, and where each page is written.

``render_page`` wraps a body in the shell — head, stylesheet, theme script — and
``render_sidebar`` is the nav that both the index and a document page carry.
``page_name`` and ``source_name`` decide the filenames. Every page renderer uses
all of it, so it sits below them.
"""

from __future__ import annotations

import html

from docir.modules.publishing.domain.site import Site
from docir.modules.publishing.infra.assets import SHELL_JS, STYLES
from docir.modules.publishing.infra.branding import Branding, brand_html
from docir.modules.publishing.infra.chips import type_dot, type_label
from docir.modules.publishing.infra.theme import THEME_SCRIPT


def page_name(doc_id: str) -> str:
    """The file a document is published at. Ids are the safe part of a filename."""
    return f"{doc_id}.html"


def source_name(doc_id: str) -> str:
    """The markdown beside the page — what "View as Markdown" opens.

    The rendered page is a projection; the body is what a reader who wants to
    quote, diff or paste the document actually needs, and asking them to
    install docir for it contradicts the whole reason the site exists. Only
    the body: the frontmatter is index input, and the page already shows every
    field of it in a form a person can read.
    """
    return f"{doc_id}.md"


def render_page(
    title: str,
    body: str,
    version: str,
    *,
    site_title: str,
    sidebar: str,
    branding: Branding,
    rail: str = "",
    stale_count: int = 0,
    diagram_scripts: str = "",
) -> str:
    """One shell for every page: top bar, corpus sidebar, content, optional rail.

    The rail sits *before* the content in the DOM — the grid places it
    visually to the right — so its panels (contents, trust, the local map)
    precede the body in source order. That is the same guarantee the old
    layout made by stacking them above the body: nothing important sits
    13,000 pixels down a long document, with or without CSS.
    """
    queue = (
        f'<a class="toplnk queue" href="index.html?is=stale" '
        f'title="documents past their review cadence">Review queue '
        f'<span class="qn">{stale_count}</span></a>'
        if stale_count
        else ""
    )
    rail_html = f'<aside class="rail">{rail}</aside>' if rail else ""
    shell = "shell" if rail else "shell norail"
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
{branding.favicon}
<script>{THEME_SCRIPT}</script>
<style>{STYLES}</style>
</head><body>
<header class="topbar">
  <button class="menubtn" id="menuBtn" aria-label="toggle navigation">☰</button>
  <a class="brand" href="index.html">{branding.mark}{brand_html(site_title)}</a>
  <button class="searchbtn" id="openPal">🔍 \
<span class="hint">Search or jump to…</span><kbd>⌘K</kbd></button>
  {queue}
  <a class="toplnk" href="graph.html">Graph</a>
  <button class="toplnk iconbtn" id="themeBtn" title="theme" aria-label="toggle theme">◐</button>
</header>
<div class="{shell}">
<nav class="sidebar" id="sidebar" aria-label="all documents">{sidebar}</nav>
{rail_html}
<main class="main">
{body}
</main>
<div class="shellfoot"><footer>Built by docir {html.escape(version)} — a derived artifact;
the markdown is the source of truth.</footer></div>
</div>
<div class="scrim" id="palScrim" hidden>
  <div class="palette" role="dialog" aria-label="search documents">
    <input id="palIn" placeholder="Search documents…" autocomplete="off">
    <div class="pres" id="palRes"></div>
    <div class="pftr"><span><kbd>↑↓</kbd> move</span><span><kbd>↵</kbd> open</span>\
<span><kbd>esc</kbd> close</span></div>
  </div>
</div>
<script>{SHELL_JS}</script>
{diagram_scripts}
</body></html>
"""


def render_sidebar(site: Site, *, active: str) -> str:
    """The whole corpus as grouped navigation, on every page.

    A document page used to have two exits — the index and the graph; the
    sidebar gives it the corpus. It is also the palette's data: the palette
    indexes these links rather than shipping a second copy, so the two cannot
    disagree. ~100 links is a few KB per page — the price of pages that work
    with no fetch.
    """
    groups: list[str] = []
    for type_name, documents in site.groups:
        items: list[str] = []
        for document in documents:
            on = ' class="on"' if document.id == active else ""
            items.append(
                f'<li><a href="{page_name(document.id)}"{on} data-doc'
                f' data-ty="{html.escape(document.type)}"'
                f' data-st="{html.escape(document.status)}">'
                f"{html.escape(document.title)}</a></li>"
            )
        groups.append(
            f'<details class="navgrp" open><summary>'
            f"{type_dot(type_name)}{html.escape(type_label(type_name, plural=True))}"
            f' <span class="n">{len(documents)}</span>'
            f'<span class="tw" aria-hidden="true">▸</span></summary>'
            f"<ul>{''.join(items)}</ul></details>"
        )
    return "".join(groups)
