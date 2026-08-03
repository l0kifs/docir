"""HTML for the published site — self-contained, offline, one file per document.

Everything is inlined: the CSS, the filter script, the favicon. A published site
has to work from ``file://`` and from a corporate Pages host with no CDN
reachable, and an asset pipeline for a few hundred lines of CSS would be a build
step to maintain rather than a feature.

Markdown is rendered with ``markdown-it-py``, which docir already installs (Rich
depends on it). Bodies come from the store's own write path, not from the
internet — but they are still escaped where they are interpolated as text rather
than rendered as markdown, because a title is not markdown and a document titled
``<script>`` should read as a title.

Four decisions here came from opening the site in a browser rather than from
reading the markup, and each is easy to undo by accident:

* **The index is a grid list, not a table.** A four-column table measured 426px
  at a 390px viewport — the page scrolled sideways — and one row was 388px tall,
  so a 105-document index showed two rows per screen. A grid reflows to one
  column.
* **Relations sit above the body.** They were underneath it: 4,068px down a
  4,596px page on one ADR, ~13,000px on the architecture document. The typed
  graph is the thing docir has and Log4brains does not, placed where nobody
  scrolls.
* **Type, status and tags look different.** Rendered as identical grey chips,
  one page read ``architecture · active · architecture · persistence ·
  retrieval`` — "architecture" appearing twice meaning two different things,
  with nothing to say which was which.
* **A body's leading ``# Title`` is dropped.** docir's own convention restates
  the title as the body's first line, which published it twice, the second one
  *larger* because a body ``h1`` outranks the page heading.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Iterable

from markdown_it import MarkdownIt

from docir.modules.publishing.domain.site import Edge, Site, SiteDocument

#: Below this width the index collapses to one column. Taken from the
#: measurement that prompted it: the old table needed 426px at a 390px viewport.
_NARROW = "40rem"

#: A document with fewer level-2 headings than this gets no table of contents —
#: two links above a short body are furniture, not navigation.
_TOC_MIN_HEADINGS = 3

#: Relation lists longer than this start collapsed. Moving relations above the
#: body fixed one problem and created another: docir's architecture document has
#: 21 inbound edges, and the panel filled the entire first screen — the reader
#: now had to scroll past the graph to reach the document. Collapsed, the count
#: is still visible without a click, which is the part that was missing before.
_RELATIONS_INLINE_MAX = 5

_STYLES = (
    """\
:root{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#e3e3e3;--accent:#0b5fff;
--chip:#f2f4f7;--warn:#8a5a00;--warn-bg:#fff5e0;--code:#f6f8fa;--panel:#fafbfc}
@media(prefers-color-scheme:dark){:root{--bg:#14161a;--fg:#e8e8e8;--muted:#9aa0aa;
--line:#2a2e35;--accent:#7aa7ff;--chip:#22262d;--warn:#ffcf70;--warn-bg:#3a2f14;
--code:#1c2027;--panel:#191c21}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:56rem;margin:0 auto;padding:2rem 1.25rem 5rem}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header.top{border-bottom:1px solid var(--line);margin-bottom:1.5rem;padding-bottom:1rem}
header.top h1{margin:0 0 .25rem;font-size:1.5rem;line-height:1.3}
.sub{color:var(--muted);font-size:.9rem}
h2.section{margin:2.25rem 0 .5rem;font-size:.8rem;text-transform:uppercase;
letter-spacing:.06em;color:var(--muted)}
#q{width:100%;padding:.6rem .75rem;font-size:1rem;border:1px solid var(--line);
border-radius:.5rem;background:var(--bg);color:var(--fg)}
ul.docs{list-style:none;margin:0;padding:0}
ul.docs li{display:grid;grid-template-columns:1fr auto;gap:.25rem 1.5rem;
padding:.85rem 0;border-bottom:1px solid var(--line)}
ul.docs a.t{font-weight:600}
.d{color:var(--muted);font-size:.92rem;margin:.15rem 0 0}
.chips{display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.45rem}
.side{display:flex;align-items:center;gap:.6rem;color:var(--muted);
font-size:.85rem;white-space:nowrap}
@media(max-width:"""
    + _NARROW
    + """){ul.docs li{grid-template-columns:1fr}.side{margin-top:.4rem}}
.chip{display:inline-block;padding:.08rem .5rem;border-radius:99px;
font-size:.78rem;white-space:nowrap;line-height:1.6}
.chip.type{background:none;border:1px solid var(--line);color:var(--muted);
text-transform:uppercase;font-size:.7rem;letter-spacing:.05em}
.chip.status{background:var(--chip);color:var(--fg);font-weight:600}
.chip.tag{background:var(--chip);color:var(--muted)}
.chip.stale{background:var(--warn-bg);color:var(--warn);font-weight:600}
.chip.archived{background:var(--chip);color:var(--muted);text-decoration:line-through}
.meta{display:flex;flex-wrap:wrap;gap:.4rem;margin:.75rem 0 1.25rem}
.banner{background:var(--warn-bg);color:var(--warn);border-radius:.5rem;
padding:.75rem 1rem;margin:1rem 0;font-size:.92rem}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:.5rem;
padding:.8rem 1rem;margin:.75rem 0;font-size:.92rem}
.panel h2,.panel summary{font-size:.72rem;text-transform:uppercase;
letter-spacing:.06em;color:var(--muted)}
.panel h2{margin:0 0 .35rem}
.panel summary{cursor:pointer}
.panel[open] summary{margin-bottom:.35rem}
.panel ul{margin:0;padding-left:1.1rem}
.panel li{margin:.15rem 0}
.kind{color:var(--muted);font-size:.85rem}
.body{margin-top:2rem}
.body h1{font-size:1.3rem;margin:2rem 0 .5rem}
.body h2{font-size:1.12rem;margin:2rem 0 .5rem;border-bottom:1px solid var(--line);
padding-bottom:.3rem}
.body h3{font-size:1rem;margin:1.5rem 0 .4rem}
.body pre{background:var(--code);padding:.9rem;border-radius:.5rem;overflow-x:auto}
.body code{background:var(--code);padding:.1rem .3rem;border-radius:.25rem;font-size:.9em}
.body pre code{background:none;padding:0}
.body table{margin:1rem 0;display:block;overflow-x:auto;border-collapse:collapse}
.body th,.body td{border:1px solid var(--line);padding:.4rem .6rem;text-align:left}
.body img{max-width:100%}
.body blockquote{margin:1rem 0;padding-left:1rem;border-left:3px solid var(--line);
color:var(--muted)}
.body .anchor{opacity:0;padding-left:.4rem;font-weight:400;color:var(--muted)}
.body h1:hover .anchor,.body h2:hover .anchor,.body h3:hover .anchor{opacity:1}
footer{margin-top:4rem;color:var(--muted);font-size:.82rem;
border-top:1px solid var(--line);padding-top:1rem}
"""
)

_FILTER_JS = """\
const rows=[...document.querySelectorAll('li[data-hay]')];
const q=document.getElementById('q'),count=document.getElementById('count');
q.addEventListener('input',()=>{
  const t=q.value.toLowerCase().trim();
  let shown=0;
  for(const r of rows){const hit=!t||r.dataset.hay.includes(t);r.hidden=!hit;if(hit)shown++;}
  for(const s of document.querySelectorAll('section[data-type]')){
    s.hidden=![...s.querySelectorAll('li[data-hay]')].some(r=>!r.hidden);
  }
  count.textContent=t?' \\u00b7 '+shown+' shown':'';
});
"""

#: An empty data: URI. Browsers request /favicon.ico on every page and log a 404
#: when it is absent; this answers it without a network request, so the page
#: stays offline-complete.
_FAVICON = '<link rel="icon" href="data:,">'


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


# -- index ------------------------------------------------------------------


def _render_index(site: Site, *, title: str, version: str) -> str:
    sections = "\n".join(_render_group(name, documents) for name, documents in site.groups)
    stale = site.stale_count
    banner = (
        f'<p class="banner">{stale} document{"s" if stale != 1 else ""} '
        "past their review cadence.</p>"
        if stale
        else ""
    )
    total = len(site.documents)
    # The filtered count starts empty and is written only while filtering: shown
    # unconditionally it read "105 documents · 105 of 105", which says the same
    # thing twice and looks like a bug.
    body = f"""\
<header class="top">
  <h1>{html.escape(title)}</h1>
  <p class="sub">{total} document{"s" if total != 1 else ""}<span id="count"></span></p>
</header>
{banner}
<input id="q" type="search" placeholder="Filter by title, description, tag, id or status…"
       aria-label="Filter documents" autocomplete="off" autofocus>
{sections}
<script>{_FILTER_JS}</script>"""
    return _page(title, body, version)


def _render_group(type_name: str, documents: Iterable[SiteDocument]) -> str:
    items = "\n".join(_render_item(document) for document in documents)
    return f"""\
<section data-type="{html.escape(type_name)}">
<h2 class="section">{html.escape(type_name)}</h2>
<ul class="docs">
{items}
</ul>
</section>"""


def _render_item(document: SiteDocument) -> str:
    # The haystack carries every field the filter searches. Built here rather
    # than in JS so the page filters with the markup alone, no fetch.
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
    owner = f" · {html.escape(document.owner)}" if document.owner else ""
    return f"""\
<li data-hay="{html.escape(haystack)}">
  <div>
    <a class="t" href="{page_name(document.id)}">{html.escape(document.title)}</a>
    <p class="d">{html.escape(document.description)}</p>
    <div class="chips">{_tag_chips(document)}{_state_chips(document)}</div>
  </div>
  <div class="side">{_status_chip(document)}\
<span>{html.escape(document.updated)}{owner}</span></div>
</li>"""


# -- document ---------------------------------------------------------------


def _render_document(document: SiteDocument, *, title: str, version: str) -> str:
    body_html, headings = render_body(document.body, drop_title=document.title)
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
<div class="meta">{_type_chip(document)}{_status_chip(document)}\
{_tag_chips(document)}{_state_chips(document)}</div>
{_render_banner(document)}
{_render_relations(document)}
{_render_toc(headings)}
<div class="body">{body_html}</div>"""
    return _page(f"{document.title} — {title}", body, version)


def _render_banner(document: SiteDocument) -> str:
    successors = document.successors
    if successors:
        links = ", ".join(_edge_link(edge) for edge in successors)
        return (
            '<p class="banner"><strong>Not the last word.</strong> '
            f"This document is superseded or contradicted by {links}.</p>"
        )
    if document.stale:
        return (
            '<p class="banner">Past its review cadence — nobody has confirmed this is '
            "still true recently.</p>"
        )
    return ""


def _render_relations(document: SiteDocument) -> str:
    """Both directions, above the body rather than under it.

    The incoming list is what no other ADR site shows: a reader landing on an
    old decision needs to know something points at it, and that edge lives on
    the *other* document's frontmatter. Under a 28,000-character body it sat
    13,000 pixels down — present, and effectively invisible.
    """
    return _relation_panel("Links to", document.outgoing) + _relation_panel(
        "Linked from", document.incoming
    )


def _relation_panel(label: str, edges: tuple[Edge, ...]) -> str:
    """One relation list, collapsed when it is long enough to bury the document.

    ``<details>`` rather than a JS toggle: it needs no script, it is keyboard
    and screen-reader accessible without any work, and the summary carries the
    count — so "21 documents link here" is legible without expanding anything.
    """
    if not edges:
        return ""
    state = " open" if len(edges) <= _RELATIONS_INLINE_MAX else ""
    return (
        f'<details class="panel"{state}>'
        f'<summary>{html.escape(label)} <span class="kind">{len(edges)}</span></summary>'
        f"<ul>{_edge_items(edges)}</ul>"
        "</details>"
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
    return f'<div class="panel"><h2>Contents</h2><ul>{items}</ul></div>'


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


# -- chips ------------------------------------------------------------------
#
# A type, a status and a tag are three different kinds of fact and were three
# identical grey pills. Each now has its own treatment, and a `title` for the
# reader who hovers rather than guesses.


def _type_chip(document: SiteDocument) -> str:
    return f'<span class="chip type" title="document type">{html.escape(document.type)}</span>'


def _status_chip(document: SiteDocument) -> str:
    return f'<span class="chip status" title="status">{html.escape(document.status)}</span>'


def _tag_chips(document: SiteDocument) -> str:
    # The `#` is the label. A word of prose per chip would be noise; the sigil
    # is read instantly and is what a tag looks like everywhere else.
    return "".join(
        f'<span class="chip tag" title="tag">#{html.escape(tag)}</span>' for tag in document.tags
    )


def _state_chips(document: SiteDocument) -> str:
    chips = ""
    if document.stale:
        chips += '<span class="chip stale" title="past its review cadence">stale</span>'
    if document.archived:
        chips += '<span class="chip archived" title="archived">archived</span>'
    return chips


# -- markdown ---------------------------------------------------------------

_HEADING_CLOSE = re.compile(r"</h([1-6])>")
_ANCHOR_GLYPH = "¶"


def render_body(text: str, *, drop_title: str = "") -> tuple[str, list[tuple[int, str, str]]]:
    """Render a body to HTML, id its headings, and report them.

    Ids come from the token stream rather than a regex over rendered HTML: the
    tokens already carry the level and the text, and rewriting generated markup
    to work out what it meant is how a renderer acquires a second parser.

    ``drop_title`` removes a leading level-1 heading that repeats the document
    title — docir's own convention restates it as the body's first line, which
    published the title twice with the second one larger.
    """
    parser = MarkdownIt("commonmark", {"linkify": False}).enable("table")
    tokens = _drop_leading_title(parser.parse(text), drop_title)

    headings: list[tuple[int, str, str]] = []
    seen: dict[str, int] = {}
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or index + 1 >= len(tokens):
            continue
        content = tokens[index + 1].content
        slug = _unique_slug(content, seen)
        token.attrSet("id", slug)
        headings.append((_level(token.tag), slug, content))

    rendered = parser.renderer.render(tokens, parser.options, {})
    return _inject_anchors(rendered, headings), headings


def _level(tag: str) -> int:
    return int(tag[1:]) if tag[1:].isdigit() else 6


def _drop_leading_title(tokens: list, title: str) -> list:
    """Drop a first-line ``# Title`` that repeats the document's own title."""
    normalized = _normalize(title)
    if not normalized or len(tokens) < 3:
        return tokens
    if (
        tokens[0].type == "heading_open"
        and tokens[0].tag == "h1"
        and _normalize(tokens[1].content) == normalized
    ):
        return tokens[3:]
    return tokens


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _unique_slug(text: str, seen: dict[str, int]) -> str:
    """A stable, readable fragment id. Repeats get a numeric suffix.

    Two sections called "Context" in one document is normal; two links pointing
    at the same one is not.
    """
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"
    count = seen.get(base, 0)
    seen[base] = count + 1
    return base if count == 0 else f"{base}-{count}"


def _inject_anchors(rendered: str, headings: list[tuple[int, str, str]]) -> str:
    """Put a link-to-this-section marker inside each heading.

    Appended at the closing tag in document order, which is the order the slugs
    were produced in — the renderer emits headings exactly once and in sequence.
    """
    slugs = iter(slug for _, slug, _ in headings)

    def replace(match: re.Match[str]) -> str:
        slug = next(slugs, None)
        if slug is None:
            return match.group(0)
        anchor = (
            f'<a class="anchor" href="#{slug}" aria-label="link to this section">'
            f"{_ANCHOR_GLYPH}</a>"
        )
        return anchor + match.group(0)

    return _HEADING_CLOSE.sub(replace, rendered)


def _page(title: str, body: str, version: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
{_FAVICON}
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
