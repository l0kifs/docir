"""One document's page: the body, its trust panel, its edges and its local map.

**Relations sit above the body**, which is a layout decision with a number
behind it. They were underneath: 4,068px down a 4,596px page on one ADR, about
13,000px on the architecture document. The typed graph is the thing docir has
and Log4brains does not, placed where nobody scrolls. The rail precedes the
content column in source order, which keeps that guarantee without CSS.
"""

from __future__ import annotations

import html
import math
from collections.abc import Mapping

from docir.modules.publishing.domain.site import INBOUND_KIND, Edge, Site, SiteDocument
from docir.modules.publishing.infra import diagrams
from docir.modules.publishing.infra.branding import Branding
from docir.modules.publishing.infra.chips import (
    id_chip,
    state_chips,
    status_chip,
    tag_chips,
    type_chip,
    type_label,
    verified_cell,
)
from docir.modules.publishing.infra.markdown import render_body
from docir.modules.publishing.infra.page_shell import (
    page_name,
    render_page,
    render_sidebar,
    source_name,
)
from docir.platform.naming.links import LinkIndex

#: A document with fewer level-2 headings than this gets no table of contents —
#: two links above a short body are furniture, not navigation.
_TOC_MIN_HEADINGS = 3


def render_document(
    document: SiteDocument,
    *,
    site: Site,
    title: str,
    version: str,
    by_id: Mapping[str, SiteDocument],
    neighbors: tuple[SiteDocument | None, SiteDocument | None],
    branding: Branding,
    runtime: bool = False,
    links: LinkIndex | None = None,
) -> str:
    # Every published document except this one: a body that names its own id
    # would otherwise get a link to the page it is already on, which reads as a
    # live cross-reference and goes nowhere. The same set gates `[[...]]`, so a
    # self-link stays text there too.
    body_html, headings = render_body(
        document.body,
        drop_title=document.title,
        known_ids=by_id.keys() - {document.id},
        links=links,
    )

    # The breadcrumb's leaf is the docir id: it is the one index a document
    # has. Sequence labels inside titles ("adr-a343140d72e2") are title text, never
    # identifiers — nothing here parses or displays them as identity. The
    # dates live in the trust panel, where they read as the signal they are
    # rather than a grey fragment under the title.
    escaped_id = html.escape(document.id)
    body = f"""\
<p class="crumbs"><a href="index.html">Documents</a> / \
<a href="index.html?type={html.escape(document.type)}">\
{html.escape(type_label(document.type, plural=True))}</a> / \
<span class="bc-id">{escaped_id}</span></p>
<header class="top">
  <h1>{html.escape(document.title)}</h1>
</header>
<p class="standfirst">{html.escape(document.description)}</p>
<div class="meta">{id_chip(document)}{type_chip(document)}{status_chip(document)}\
{tag_chips(document)}{state_chips(document)}</div>
<div class="actions">\
<button class="abtn" data-copy="docir get {escaped_id}">\
⧉ <code>docir get {escaped_id}</code></button>\
<a class="abtn" href="{source_name(document.id)}">View as Markdown</a>\
<a class="abtn" href="graph.html#{escaped_id}">◉ View in graph</a></div>
{_render_banner(document)}
<div class="body">{body_html}</div>
{_render_pn(neighbors)}
<p class="foot-meta"><span>To amend: \
<button data-copy="docir update {escaped_id}"><code>docir update {escaped_id}</code></button> \
</span><span>Re-verify: <button data-copy="docir update {escaped_id} --verified">\
<code>docir update {escaped_id} --verified</code></button></span></p>"""
    # Contents, trust, the map, then relations. The map is the compressed
    # answer to "what is this next to?" and the list is the long one; reading
    # order puts the glance first, and an outlier's 21 inbound edges then sit
    # below everything else rather than between the reader and the map.
    rail = (
        _render_toc(headings)
        + _render_trust(document)
        + _render_governs(document)
        + _render_local_map(document, by_id)
        + _render_relations(document, by_id)
    )
    return render_page(
        f"{document.title} — {title}",
        body,
        version,
        site_title=title,
        sidebar=render_sidebar(site, active=document.id),
        branding=branding,
        rail=rail,
        stale_count=site.stale_count,
        # Only a page that has a diagram loads the runtime: it is megabytes,
        # and most documents have none.
        diagram_scripts=(
            diagrams.script_tags() if runtime and diagrams.has_diagram(body_html) else ""
        ),
    )


def _render_trust(document: SiteDocument) -> str:
    """Owner and verification as a panel — the trust signal, not a grey
    fragment in a dates line. Only what the payload carries: the site
    receives no schema, so there is no cadence or due date to invent — the
    staleness flag beneath the rows is the derived signal, computed where the
    cadence actually lives, and a rendered "review due 2027-01-30" would be
    the renderer guessing at it."""
    rows = [
        ("Owner", document.owner or "—"),
        ("Verified", verified_cell(document)),
        ("Created", document.created),
        ("Updated", document.updated),
    ]
    body = "".join(
        f'<div class="trow"><span class="k">{key}</span>'
        f'<span class="v">{html.escape(value)}</span></div>'
        for key, value in rows
    )
    flag = '<div class="trow stale-note">⚠ past its review cadence</div>' if document.stale else ""
    return f'<div class="railgrp"><h2>Trust</h2><div class="trust">{body}{flag}</div></div>'


def _render_governs(document: SiteDocument) -> str:
    """The code the document claims to govern, or nothing at all.

    Rendered as plain patterns and never as links: the site is a static
    projection of the store, which knows the globs but not the repository they
    resolve against — a link would be a guess at a forge URL, and a "3 files"
    count would be a guess at a working tree. Absent for the documents that
    declare none, like every other optional panel here.
    """
    if not document.code:
        return ""
    items = "".join(f"<li><code>{html.escape(pattern)}</code></li>" for pattern in document.code)
    return f'<div class="railgrp"><h2>Governs</h2><ul>{items}</ul></div>'


def _render_local_map(document: SiteDocument, by_id: Mapping[str, SiteDocument]) -> str:
    """The document's 1-hop neighbourhood as a small deterministic map.

    Successors first, then outgoing, then remaining inbound — the order a
    reader needs them — capped at five so the panel stays a glance, not a
    diagram. Dangling targets are excluded exactly as the full graph excludes
    them (the relation lists already show the broken reference). Every
    neighbour is a link, and the footer deep-links into the full map with
    this document pinned.
    """
    seen = {document.id}
    edges: list[Edge] = []
    for edge in (*document.successors, *document.outgoing, *document.incoming):
        if edge.title is None or edge.target in seen:
            continue
        seen.add(edge.target)
        edges.append(edge)
        if len(edges) == 5:
            break
    if not edges:
        return ""
    cx, cy, radius = 120.0, 98.0, 72.0
    lines: list[str] = []
    nodes: list[str] = []
    for index, edge in enumerate(edges):
        angle = math.radians(-90 + index * 360 / len(edges))
        x, y = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
        # Kind labels sit at 45% of the spoke — far enough from the centre
        # label and the neighbour names that five of each stay legible.
        mid_x, mid_y = cx + (x - cx) * 0.45, cy + (y - cy) * 0.45
        target = by_id.get(edge.target)
        target_type = target.type if target else ""
        colour = (
            f"var(--t-{html.escape(target_type)},var(--muted))" if target_type else "var(--muted)"
        )
        label_y = y - 12 if y < cy else y + 20
        lines.append(f'<line class="edge" x1="{cx:.0f}" y1="{cy:.0f}" x2="{x:.0f}" y2="{y:.0f}"/>')
        nodes.append(
            f'<text class="elbl" x="{mid_x:.0f}" y="{mid_y:.0f}" text-anchor="middle">'
            f"{html.escape(edge.kind)}</text>"
            f'<a href="{page_name(edge.target)}">'
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="6.5" fill="{colour}"/>'
            f'<text class="nlbl" x="{x:.0f}" y="{label_y:.0f}" text-anchor="middle">'
            f"{html.escape(_short(edge.title or edge.target, 16))}</text></a>"
        )
    centre = f"var(--t-{html.escape(document.type)},var(--muted))"
    return (
        '<div class="railgrp"><h2>Local map · 1 hop</h2><div class="map-box">'
        '<svg viewBox="0 0 240 200" role="img" aria-label="1-hop relation map">'
        f"{''.join(lines)}{''.join(nodes)}"
        f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="9" fill="{centre}"/>'
        f'<circle class="ring" cx="{cx:.0f}" cy="{cy:.0f}" r="13"/>'
        f'<text class="nlbl ctr" x="{cx:.0f}" y="{cy + 28:.0f}" text-anchor="middle">'
        f"{html.escape(_short(document.title, 18))}</text></svg>"
        f'<a class="full" href="graph.html#{html.escape(document.id)}">'
        "Open in the full graph →</a></div></div>"
    )


def _render_pn(neighbors: tuple[SiteDocument | None, SiteDocument | None]) -> str:
    """Previous/next within the type, in the listing's own order."""
    prev_doc, next_doc = neighbors
    if prev_doc is None and next_doc is None:
        return ""
    left = (
        f'<a href="{page_name(prev_doc.id)}"><span class="lbl">← previous</span>'
        f"{html.escape(prev_doc.title)}</a>"
        if prev_doc
        else "<span></span>"
    )
    right = (
        f'<a class="next" href="{page_name(next_doc.id)}"><span class="lbl">next →</span>'
        f"{html.escape(next_doc.title)}</a>"
        if next_doc
        else "<span></span>"
    )
    return f'<nav class="pn">{left}{right}</nav>'


def _render_banner(document: SiteDocument) -> str:
    """The one thing a reader must not miss, before the body.

    Two facts can be true at once — a superseded document is often also
    overdue — and the successor is the more urgent of the two, so staleness
    rides as a second line under it rather than losing to it. The warning
    glyph is a separate flex column: inline, a wrapped second line tucked
    under it and the block stopped reading as a callout.
    """
    stale_note = (
        '<span class="also">Also past its review cadence — nobody has confirmed '
        "this is still true recently.</span>"
        if document.stale
        else ""
    )
    successors = document.successors
    if successors:
        links = ", ".join(_edge_link(edge) for edge in successors)
        return (
            '<p class="banner"><span class="ic">⚠</span><span><b>Not the last word.</b> '
            f"This document is superseded or contradicted by {links}.{stale_note}</span></p>"
        )
    if document.stale:
        return (
            '<p class="banner"><span class="ic">⚠</span><span><b>Past its review '
            "cadence.</b> Nobody has confirmed this is still true recently.</span></p>"
        )
    return ""


def _render_relations(document: SiteDocument, by_id: Mapping[str, SiteDocument]) -> str:
    """Both directions, above the body rather than under it.

    The incoming list is what no other ADR site shows: a reader landing on an
    old decision needs to know something points at it, and that edge lives on
    the *other* document's frontmatter. Under a 28,000-character body it sat
    13,000 pixels down — present, and effectively invisible. The panel lives
    in the rail, which precedes the body in source order — the same guarantee
    in a column of its own.

    One panel, not two: the *direction* rides on the kind label rather than
    on a heading above it, because "refines" over an inbound edge says the
    opposite of the truth. Outgoing reads `refines →`, inbound reads
    `← refined by`, so a row means the same thing whichever list it is in.

    The list is open, not a `<details>` behind its own count. Collapsing was
    the fix while relations sat first in the rail and docir's architecture
    document put 21 of them between the reader and everything below; last in
    the rail there is nothing below to push away, and a click to see what a
    document connects to is a click to see the thing the typed graph exists
    for. The count stays in the heading, which is what the summary was
    carrying.
    """
    groups: dict[str, list[Edge]] = {}
    for edge in document.outgoing:
        groups.setdefault(f"{edge.kind.replace('_', ' ')} →", []).append(edge)
    for edge in document.incoming:
        inbound = INBOUND_KIND.get(edge.kind, edge.kind.replace("_", " "))
        groups.setdefault(f"← {inbound}", []).append(edge)
    if not groups:
        return ""
    total = len(document.outgoing) + len(document.incoming)
    inner = "".join(
        f'<span class="kind">{html.escape(label)}</span>'
        f"<ul>{''.join(f'<li>{_edge_link(edge, by_id)}</li>' for edge in edges)}</ul>"
        for label, edges in groups.items()
    )
    return (
        f'<div class="railgrp rel"><h2>Relations <span class="n">{total}</span></h2>{inner}</div>'
    )


def _render_toc(headings: list[tuple[int, str, str]]) -> str:
    """Section navigation — the site's answer to ``get --section``.

    Level-2 headings only: a nested outline of a 25-heading document is a second
    document to read.
    """
    sections = [(slug, text) for level, slug, text in headings if level == 2]
    if len(sections) < _TOC_MIN_HEADINGS:
        return ""
    items = "".join(
        f'<li><a href="#{slug}">{html.escape(text)}</a></li>' for slug, text in sections
    )
    return f'<div class="railgrp toc"><h2>On this page</h2><ul>{items}</ul></div>'


def _edge_link(edge: Edge, by_id: Mapping[str, SiteDocument] | None = None) -> str:
    """A link, or the bare id when the target is not in the corpus.

    A dangling edge stays visible: the site shows the same broken reference
    `docir check` reports, rather than hiding a defect behind a missing row.
    A resolvable link carries the target's summary as data attributes, so the
    hover preview answers "what is this?" without the click.
    """
    if edge.title is None:
        return f'<span class="dead" title="not in this corpus">{html.escape(edge.target)}</span>'
    target = by_id.get(edge.target) if by_id else None
    preview = ""
    if target is not None:
        meta = f"{target.type} · {target.status} · {target.updated}"
        preview = (
            f' data-pt="{html.escape(target.title)}"'
            f' data-pd="{html.escape(target.description)}"'
            f' data-pm="{html.escape(meta)}"'
        )
    return f'<a href="{page_name(edge.target)}"{preview}>{html.escape(edge.title)}</a>'


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
