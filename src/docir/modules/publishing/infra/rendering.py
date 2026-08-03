"""HTML for the published site — self-contained, offline, one file per document.

Everything is inlined: the CSS, the search index, the theme toggle. A published
site has to work from ``file://`` and from a corporate Pages host with no CDN
reachable, and an asset pipeline for a few hundred lines of CSS would be a build
step to maintain rather than a feature.

Markdown is rendered with ``markdown-it-py``, which docir already installs (Rich
depends on it). Bodies come from the store's own write path, not from the
internet — but they are still escaped where they are interpolated as text rather
than rendered as markdown, because a title is not markdown and a document titled
``<script>`` should read as a title.
"""

from __future__ import annotations

import html
import json
from collections.abc import Iterable

from markdown_it import MarkdownIt

from docir.modules.publishing.domain.site import Edge, Site, SiteDocument

_STYLES = """\
:root{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#e3e3e3;--accent:#0b5fff;
--chip:#f2f4f7;--warn:#8a5a00;--warn-bg:#fff5e0;--code:#f6f8fa}
@media(prefers-color-scheme:dark){:root{--bg:#14161a;--fg:#e8e8e8;--muted:#9aa0aa;
--line:#2a2e35;--accent:#7aa7ff;--chip:#22262d;--warn:#ffcf70;--warn-bg:#3a2f14;--code:#1c2027}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:56rem;margin:0 auto;padding:2rem 1.25rem 5rem}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header.top{border-bottom:1px solid var(--line);margin-bottom:2rem;padding-bottom:1rem}
header.top h1{margin:0 0 .25rem;font-size:1.5rem}
.sub{color:var(--muted);font-size:.9rem}
h2{margin:2.5rem 0 .75rem;font-size:1.15rem;border-bottom:1px solid var(--line);
padding-bottom:.35rem}
table{width:100%;border-collapse:collapse;font-size:.92rem}
th,td{text-align:left;padding:.5rem .6rem;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:.8rem;text-transform:uppercase;letter-spacing:.04em}
td.desc{color:var(--muted)}
.chip{display:inline-block;padding:.1rem .5rem;border-radius:99px;background:var(--chip);
font-size:.78rem;color:var(--muted);white-space:nowrap}
.chip.stale{background:var(--warn-bg);color:var(--warn)}
.chip.archived{opacity:.65;text-decoration:line-through}
#q{width:100%;padding:.6rem .75rem;font-size:1rem;border:1px solid var(--line);
border-radius:.5rem;background:var(--bg);color:var(--fg);margin-bottom:.5rem}
.meta{display:flex;flex-wrap:wrap;gap:.4rem;margin:.75rem 0 1.5rem}
.banner{background:var(--warn-bg);color:var(--warn);border-radius:.5rem;padding:.75rem 1rem;
margin:1rem 0;font-size:.92rem}
.body{margin-top:2rem}
.body pre{background:var(--code);padding:.9rem;border-radius:.5rem;overflow-x:auto}
.body code{background:var(--code);padding:.1rem .3rem;border-radius:.25rem;font-size:.9em}
.body pre code{background:none;padding:0}
.body table{margin:1rem 0;display:block;overflow-x:auto}
.body img{max-width:100%}
.edges{margin-top:2.5rem;border-top:1px solid var(--line);padding-top:1rem}
.edges ul{margin:.25rem 0 1rem;padding-left:1.1rem}
.edges li{margin:.2rem 0}
.kind{color:var(--muted);font-size:.85rem}
footer{margin-top:4rem;color:var(--muted);font-size:.82rem;
border-top:1px solid var(--line);padding-top:1rem}
"""

_SEARCH_JS = """\
const rows=[...document.querySelectorAll('tbody tr')];
const q=document.getElementById('q');
q.addEventListener('input',()=>{
  const t=q.value.toLowerCase().trim();
  let shown=0;
  for(const r of rows){
    const hit=!t||r.dataset.hay.includes(t);
    r.hidden=!hit; if(hit)shown++;
  }
  for(const s of document.querySelectorAll('section[data-type]')){
    s.hidden=![...s.querySelectorAll('tbody tr')].some(r=>!r.hidden);
  }
  document.getElementById('count').textContent=shown+' of '+rows.length;
});
"""


def render_site(site: Site, *, title: str, version: str) -> dict[str, str]:
    """Render the whole site as ``relative path -> file contents``.

    Returning content rather than writing it keeps this layer free of the
    filesystem, so a test can assert on the HTML without a temp directory and
    the writer has exactly one job.
    """
    pages = {"index.html": _render_index(site, title=title, version=version)}
    for document in site.documents:
        pages[page_name(document.id)] = _render_document(document, title=title, version=version)
    return pages


def page_name(doc_id: str) -> str:
    """The file a document is published at. Ids are the safe part of a filename."""
    return f"{doc_id}.html"


# -- pages ------------------------------------------------------------------


def _render_index(site: Site, *, title: str, version: str) -> str:
    sections = "\n".join(_render_group(name, documents) for name, documents in site.groups)
    stale = site.stale_count
    banner = (
        f'<p class="banner">{stale} document{"s" if stale != 1 else ""} '
        "past their review cadence.</p>"
        if stale
        else ""
    )
    body = f"""\
<header class="top">
  <h1>{html.escape(title)}</h1>
  <p class="sub">{len(site.documents)} documents · <span id="count">\
{len(site.documents)} of {len(site.documents)}</span></p>
</header>
{banner}
<input id="q" type="search" placeholder="Filter by title, description, tag, id or status…"
       autocomplete="off" autofocus>
{sections}
<script>{_SEARCH_JS}</script>"""
    return _page(title, body, version)


def _render_group(type_name: str, documents: Iterable[SiteDocument]) -> str:
    rows = "\n".join(_render_row(document) for document in documents)
    return f"""\
<section data-type="{html.escape(type_name)}">
<h2>{html.escape(type_name)}</h2>
<table><thead><tr><th>Title</th><th>Status</th><th>Updated</th><th>Owner</th></tr></thead>
<tbody>
{rows}
</tbody></table>
</section>"""


def _render_row(document: SiteDocument) -> str:
    # The haystack carries every field the filter box searches. Built here
    # rather than in JS so the page works with the markup alone.
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
    chips = "".join(
        f'<span class="chip">{html.escape(tag)}</span>' for tag in document.tags
    ) + _state_chips(document)
    return f"""\
<tr data-hay="{html.escape(haystack)}">
  <td><a href="{page_name(document.id)}">{html.escape(document.title)}</a>
      <div class="desc">{html.escape(document.description)}</div>
      <div class="meta">{chips}</div></td>
  <td><span class="chip">{html.escape(document.status)}</span></td>
  <td>{html.escape(document.updated)}</td>
  <td>{html.escape(document.owner)}</td>
</tr>"""


def _state_chips(document: SiteDocument) -> str:
    chips = ""
    if document.stale:
        chips += '<span class="chip stale">stale</span>'
    if document.archived:
        chips += '<span class="chip archived">archived</span>'
    return chips


def _render_document(document: SiteDocument, *, title: str, version: str) -> str:
    successors = document.successors
    banner = ""
    if successors:
        links = ", ".join(_edge_link(edge) for edge in successors)
        banner = (
            f'<p class="banner"><strong>Not the last word.</strong> '
            f"This document is superseded or contradicted by {links}.</p>"
        )
    elif document.stale:
        banner = (
            '<p class="banner">Past its review cadence — nobody has confirmed this is '
            "still true recently.</p>"
        )

    meta = "".join(
        [
            f'<span class="chip">{html.escape(document.type)}</span>',
            f'<span class="chip">{html.escape(document.status)}</span>',
            *(f'<span class="chip">{html.escape(tag)}</span>' for tag in document.tags),
            _state_chips(document),
        ]
    )
    dates = f"created {html.escape(document.created)} · updated {html.escape(document.updated)}"
    if document.verified:
        dates += f" · verified {html.escape(document.verified)}"
    if document.owner:
        dates += f" · owner {html.escape(document.owner)}"

    body = f"""\
<p class="sub"><a href="index.html">← all documents</a></p>
<header class="top">
  <h1>{html.escape(document.title)}</h1>
  <p class="sub">{html.escape(document.id)} · {dates}</p>
</header>
<p>{html.escape(document.description)}</p>
<div class="meta">{meta}</div>
{banner}
<div class="body">{_markdown(document.body)}</div>
{_render_edges(document)}"""
    return _page(f"{document.title} — {title}", body, version)


def _render_edges(document: SiteDocument) -> str:
    """Both directions, because the graph is stored one way and read both.

    The incoming list is what no other ADR site shows: a reader landing on an
    old decision needs to know something points at it, and that edge lives on
    the *other* document's frontmatter.
    """
    blocks = []
    if document.outgoing:
        blocks.append("<h2>Links to</h2><ul>" + _edge_items(document.outgoing) + "</ul>")
    if document.incoming:
        blocks.append("<h2>Linked from</h2><ul>" + _edge_items(document.incoming) + "</ul>")
    if not blocks:
        return ""
    return '<div class="edges">' + "".join(blocks) + "</div>"


def _edge_items(edges: Iterable[Edge]) -> str:
    return "".join(
        f'<li>{_edge_link(edge)} <span class="kind">{html.escape(edge.kind)}</span></li>'
        for edge in edges
    )


def _edge_link(edge: Edge) -> str:
    """A link, or the bare id when the target is not in the corpus.

    A dangling edge stays visible: the site shows the same broken reference
    `docir check` reports, rather than hiding a defect behind a missing row.
    """
    if edge.title is None:
        return f'<span title="not in this corpus">{html.escape(edge.target)}</span>'
    return f'<a href="{page_name(edge.target)}">{html.escape(edge.title)}</a>'


def _markdown(text: str) -> str:
    return MarkdownIt("commonmark", {"linkify": False}).enable("table").render(text)


def _page(title: str, body: str, version: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_STYLES}</style>
</head><body><div class="wrap">
{body}
<footer>Built by docir {html.escape(version)} — a derived artifact; the markdown is the
source of truth.</footer>
</div></body></html>
"""


def render_search_index(site: Site) -> str:
    """A JSON index beside the pages, for anything that wants to search the site.

    Not used by the built-in filter, which works off the markup so the page
    needs no fetch and works from ``file://``. Emitted because a published
    corpus is a thing other tools reasonably want to read.
    """
    return json.dumps(
        [
            {
                "id": document.id,
                "title": document.title,
                "description": document.description,
                "type": document.type,
                "status": document.status,
                "tags": list(document.tags),
                "url": page_name(document.id),
            }
            for document in site.documents
        ],
        separators=(",", ":"),
        ensure_ascii=False,
    )
