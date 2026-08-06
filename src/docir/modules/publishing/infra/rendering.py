"""HTML for the published site — self-contained, offline, one file per document.

Everything is inlined: the CSS, the filter script, the mark, the favicon. A
published site has to work from ``file://`` and from a corporate Pages host
with no CDN reachable, and an asset pipeline for a few hundred lines of CSS
would be a build step to maintain rather than a feature.

Markdown is rendered with ``markdown-it-py``, which docir already installs (Rich
depends on it). Bodies come from the store's own write path, not from the
internet — but they are still escaped where they are interpolated as text rather
than rendered as markdown, because a title is not markdown and a document titled
``<script>`` should read as a title.

Several decisions here came from opening the site in a browser rather than from
reading the markup, and each is easy to undo by accident:

* **The index is a grid list, not a table.** A four-column table measured 426px
  at a 390px viewport — the page scrolled sideways — and one row was 388px tall,
  so a 105-document index showed two rows per screen. A grid reflows to one
  column.
* **Relations sit above the body.** They were underneath it: 4,068px down a
  4,596px page on one ADR, ~13,000px on the architecture document. The typed
  graph is the thing docir has and Log4brains does not, placed where nobody
  scrolls. The rail precedes the content column in source order, which keeps
  that guarantee without CSS.
* **Type, status and tags look different.** Rendered as identical grey chips,
  one page read ``architecture · active · architecture · persistence ·
  retrieval`` — "architecture" appearing twice meaning two different things,
  with nothing to say which was which.
* **A body's leading ``# Title`` is dropped.** docir's own convention restates
  the title as the body's first line, which published it twice, the second one
  *larger* because a body ``h1`` outranks the page heading.
* **Class names in here are scoped.** A bare ``.sub`` utility, left behind when
  the landing's stats line was renamed, captured ``.brand .sub`` and shrank the
  wordmark's tail on the pages but not on the graph, whose stylesheet has no
  such rule. One brand, two sizes.
"""

from __future__ import annotations

import html
import json
import math
import re
from collections.abc import Collection, Iterable, Mapping

from markdown_it import MarkdownIt
from markdown_it.token import Token

from docir.modules.publishing.domain.site import INBOUND_KIND, Edge, Site, SiteDocument
from docir.modules.publishing.infra.branding import DOCIR_BRANDING, Branding, brand_html
from docir.modules.publishing.infra.graph import render_graph_page
from docir.modules.publishing.infra.highlight import highlight, language_label
from docir.modules.publishing.infra.theme import CSS_TOKENS, THEME_SCRIPT, THEME_TOGGLE_JS

#: Below this width the index collapses to one column. Taken from the
#: measurement that prompted it: the old table needed 426px at a 390px viewport.
_NARROW = "40rem"

#: A document with fewer level-2 headings than this gets no table of contents —
#: two links above a short body are furniture, not navigation.
_TOC_MIN_HEADINGS = 3

#: Semantic colour per status *name*. The site receives no schema, so statuses
#: are recognised the way the graph page recognises inactive ones — by the
#: bundled profiles' vocabularies. An unknown status renders as the neutral
#: chip rather than guessing a meaning; a wrong colour is worse than none.
_STATUS_CLASS = {
    "accepted": "st-good",
    "active": "st-good",
    "open": "st-good",
    "published": "st-good",
    "supported": "st-good",
    "superseded": "st-warn",
    "deprecated": "st-warn",
    "breached": "st-warn",
    "rejected": "st-bad",
    "resolved": "st-done",
    "complete": "st-done",
}

_STYLES = (
    CSS_TOKENS
    + """\
*{box-sizing:border-box}
/* The [hidden] attribute only maps to display:none in the UA stylesheet, and
   any author display (the grid rows, the flex facet labels) overrides it —
   so a filtered-out row stayed visible whenever its section did not hide
   with it. The reset makes hidden mean hidden everywhere. */
[hidden]{display:none!important}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,sans-serif;
-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
code,kbd{font-family:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
/* ---- the shell: top bar, corpus sidebar, content, optional rail ---- */
.topbar{position:sticky;top:0;z-index:30;display:flex;align-items:center;gap:.9rem;
height:56px;padding:0 1.25rem;background:var(--bg);border-bottom:1px solid var(--line)}
.menubtn{display:none;border:1px solid var(--line);border-radius:8px;background:none;
color:var(--muted);cursor:pointer;font:inherit;padding:.15rem .55rem}
.brand{display:flex;align-items:center;gap:.55rem;font-weight:600;color:var(--fg);
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.brand:hover{text-decoration:none}
/* The tail is the same size as the wordmark, lighter and muted — not smaller.
   A bare `.sub{font-size:.9rem}` utility (the landing's old stats line, long
   since renamed) captured this selector too, so the same brand measured
   14.4px on a page and 16px on the graph, which has no such rule. Scoped
   names only in here: a two-word class is a collision waiting for a page that
   does not share the intent. */
.brand .sub{color:var(--muted);font-weight:400}
/* The mark is supplied art (docir's own, or the publisher's), so this sizes
   it and nothing else. Height-locked with a free width: docir's mark is
   square but a publisher's is as likely to be a wordmark lockup, and a fixed
   width would squash it. The max-width stops an extreme one from pushing the
   search box off the bar. `color` is set here rather than inherited because
   docir's mark draws its bracket in `currentColor` and the mark sits inside
   an <a>: inheriting made the bracket accent-blue on the graph page, where
   the link is not the same colour as the text. */
.brandmark{height:22px;width:auto;max-width:10rem;flex:none;display:block;
object-fit:contain;color:var(--fg)}
.searchbtn{display:flex;align-items:center;gap:.6rem;margin-left:auto;cursor:pointer;
border:1px solid var(--line);border-radius:8px;background:var(--chip);color:var(--muted);
font:inherit;font-size:.88rem;padding:.38rem .6rem .38rem .75rem;min-width:15rem}
.searchbtn:hover{border-color:var(--faint)}
.searchbtn kbd{margin-left:auto;border:1px solid var(--line);border-bottom-width:2px;
border-radius:5px;padding:0 .35rem;font-size:.72rem;background:var(--bg);color:var(--muted)}
.toplnk{color:var(--muted);font-size:.9rem;white-space:nowrap;border:0;background:none;
cursor:pointer;font-family:inherit;padding:0}
.toplnk:hover{color:var(--fg);text-decoration:none}
.iconbtn{width:34px;height:34px;border:1px solid var(--line);border-radius:8px;
display:inline-flex;align-items:center;justify-content:center;flex:none;font-size:.95rem}
.iconbtn:hover{background:var(--chip)}
.queue{display:inline-flex;align-items:center;gap:.4rem}
.queue .qn{background:var(--warn-bg);color:var(--warn);font-weight:600;font-size:.75rem;
border-radius:99px;padding:.05rem .45rem}
.shell{display:grid;grid-template-columns:260px minmax(0,1fr) 240px;gap:0 2.25rem;
max-width:1400px;margin:0 auto;align-items:start}
.shell.norail{grid-template-columns:260px minmax(0,1fr)}
.sidebar{grid-column:1;position:sticky;top:56px;max-height:calc(100vh - 56px);
overflow-y:auto;padding:1.25rem .8rem 3rem 1.25rem;border-right:1px solid var(--line-soft);
font-size:.86rem}
.rail{grid-column:3;grid-row:1;position:sticky;top:56px;max-height:calc(100vh - 56px);
overflow-y:auto;padding:1.6rem 1.25rem 3rem 0;font-size:.85rem}
.main{grid-column:2;grid-row:1;max-width:45rem;width:100%;margin:0 auto;
padding:1.75rem 1.25rem 3rem;min-width:0}
.shellfoot{grid-column:2;grid-row:2;max-width:45rem;width:100%;margin:0 auto;
padding:0 1.25rem 3rem}
.navgrp{margin:0 0 .35rem}
.navgrp>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:.45rem;
padding:.3rem .5rem;border-radius:6px;font-weight:600;color:var(--fg);user-select:none}
.navgrp>summary::-webkit-details-marker{display:none}
.navgrp>summary:hover{background:var(--chip)}
.navgrp>summary .n{color:var(--faint);font-weight:400;font-size:.78rem}
/* The twisty is the only thing that says a group collapses. Without it the
   summary reads as a heading and nobody discovers the fold. */
.navgrp>summary .tw{margin-left:auto;color:var(--faint);font-size:.7rem;
transition:transform .15s;transform:rotate(0)}
.navgrp[open]>summary .tw{transform:rotate(90deg)}
.navgrp .dot,.pit .dot{width:8px;height:8px;border-radius:99px;flex:none}
.navgrp ul{list-style:none;margin:.1rem 0 .5rem;padding:0 0 0 .35rem}
.navgrp li a{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
padding:.28rem .5rem;border-left:2px solid transparent;color:var(--muted);
border-radius:0 6px 6px 0;line-height:1.4}
.navgrp li a:hover{background:var(--chip);color:var(--fg);text-decoration:none}
.navgrp li a.on{border-left-color:var(--accent);color:var(--accent);font-weight:600;
background:color-mix(in srgb,var(--accent) 7%,transparent)}
/* ---- landing ---- */
header.top{margin-bottom:1.5rem}
header.top h1{margin:0 0 .3rem;font-size:2rem;line-height:1.25;letter-spacing:-.01em}
.standfirst{margin:.2rem 0 0;color:var(--muted);font-size:1.05rem;line-height:1.55}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:.75rem;margin:1.5rem 0}
.tile{display:block;border:1px solid var(--line);border-radius:10px;
padding:.8rem .95rem;color:var(--fg);background:var(--bg)}
.tile .v{display:block;font-size:1.45rem;font-weight:650;line-height:1.2}
.tile .k{display:block;color:var(--muted);font-size:.8rem}
.tile.linky{border-color:color-mix(in srgb,var(--warn) 35%,var(--line))}
.tile.linky .v{color:var(--warn)}
.tile.linky:hover{background:var(--chip);text-decoration:none}
h2.section{display:flex;align-items:center;gap:.55rem;margin:2.25rem 0 .4rem;
font-size:.78rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}
#q{width:100%;padding:.6rem .85rem;font-size:.95rem;border:1px solid var(--line);
border-radius:8px;background:var(--bg);color:var(--fg)}
#q::placeholder{color:var(--faint)}
/* ---- facets ---- */
.fbar{display:flex;gap:.5rem;margin:.75rem 0 0;flex-wrap:wrap;align-items:center}
.facet{position:relative}
.facet>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:.35rem;
padding:.34rem .7rem;font-size:.84rem;border:1px solid var(--line);border-radius:8px;
color:var(--muted);user-select:none;white-space:nowrap;background:var(--bg)}
.facet>summary::-webkit-details-marker{display:none}
.facet>summary::after{content:"\\25be";font-size:.66rem;color:var(--faint)}
.facet>summary:hover{background:var(--chip)}
.facet[open]>summary{border-color:var(--faint);color:var(--fg)}
.facet .sum,#tsum,#ssum,#osum,#dsum{color:var(--accent);font-weight:600}
.fopts{position:absolute;top:calc(100% + .35rem);left:0;z-index:40;background:var(--bg);
border:1px solid var(--line);border-radius:10px;box-shadow:var(--shadow);
padding:.55rem .65rem;min-width:13rem;display:flex;flex-direction:column;gap:.15rem}
.fopts label{display:flex;gap:.5rem;align-items:center;font-size:.86rem;
padding:.22rem .35rem;border-radius:6px;cursor:pointer;white-space:nowrap}
.fopts label:hover{background:var(--chip)}
.fopts input{accent-color:var(--accent)}
.fopts .n{color:var(--faint);font-size:.76rem;margin-left:auto;padding-left:1rem;
font-variant-numeric:tabular-nums}
.fopts label.ghost{opacity:.45}
.fopts label.ghost input{cursor:not-allowed}
.drange{display:flex;flex-direction:column;gap:.35rem;border-top:1px solid var(--line-soft);
padding-top:.45rem;margin-top:.2rem;font-size:.82rem;color:var(--muted)}
.drange input[type=date]{padding:.25rem .4rem;border:1px solid var(--line);
border-radius:6px;background:var(--bg);color:var(--fg);font:inherit;font-size:.8rem}
#fclear{color:var(--accent);font:inherit;font-size:.84rem;border:0;background:none;
cursor:pointer;padding:0}
/* The filtered count belongs beside the controls that produced it. In the
   header it sat under the corpus total and read as a second, contradictory
   figure. */
#fcount{color:var(--faint);font-size:.84rem;margin-left:auto;
font-variant-numeric:tabular-nums}
#staleTgl{border:1px solid var(--line);border-radius:8px;background:var(--bg);
color:var(--muted);cursor:pointer;font:inherit;font-size:.84rem;padding:.34rem .7rem;
white-space:nowrap}
#staleTgl:hover{background:var(--chip)}
#staleTgl.on{background:var(--warn-bg);color:var(--warn);border-color:var(--warn)}
.fchips{display:flex;flex-wrap:wrap;gap:.4rem;margin:.65rem 0 0}
.fchip{display:inline-flex;align-items:center;gap:.3rem;border:1px solid var(--line);
border-radius:999px;background:var(--chip);padding:.16rem .3rem .16rem .7rem;
font-size:.8rem;color:var(--fg)}
.fchip.neg{border-color:color-mix(in srgb,var(--bad) 45%,var(--line));color:var(--bad)}
.fchip .x{width:1.15rem;height:1.15rem;border:0;border-radius:999px;background:none;
color:var(--faint);cursor:pointer;font:inherit;line-height:1;padding:0;display:inline-flex;
align-items:center;justify-content:center}
.fchip .x:hover{background:var(--bad-bg);color:var(--bad)}
.views{display:flex;gap:1rem;align-items:baseline;margin:1rem 0 0;font-size:.84rem;
flex-wrap:wrap}
.views .vlbl{color:var(--faint);font-size:.7rem;text-transform:uppercase;
letter-spacing:.07em}
.views button{border:0;background:none;color:var(--muted);cursor:pointer;font:inherit;
font-size:.84rem;padding:.1rem 0;border-bottom:2px solid transparent}
.views button:hover{color:var(--fg)}
.views button.on{color:var(--accent);border-bottom-color:var(--accent);font-weight:600}
.norec{margin-top:2rem;color:var(--muted)}
.norec p{margin:0 0 .6rem;color:var(--faint)}
.norec button{border:1px solid var(--line);border-radius:8px;background:none;
color:var(--accent);cursor:pointer;font:inherit;font-size:.84rem;padding:.34rem .8rem;
margin-right:.5rem}
.norec button:hover{background:var(--chip)}
/* ---- document listing ---- */
ul.docs{list-style:none;margin:0;padding:0}
ul.docs li{display:grid;grid-template-columns:1fr auto;gap:.1rem 1.25rem;
padding:.7rem .6rem;margin:0 -.6rem;border-radius:8px;
border-bottom:1px solid var(--line-soft)}
ul.docs li:hover{background:var(--chip)}
ul.docs a.t{font-weight:600}
.d{color:var(--muted);font-size:.87rem;margin:.05rem 0 0;line-height:1.5}
.chips{display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.45rem}
.side{grid-row:1/span 2;grid-column:2;display:flex;align-items:center;gap:.6rem;
color:var(--faint);font-size:.8rem;white-space:nowrap}
.side time{font-variant-numeric:tabular-nums}
/* ---- chips ---- */
.chip{display:inline-flex;align-items:center;gap:.35rem;padding:.1rem .6rem;
border-radius:999px;font-size:.76rem;font-weight:600;white-space:nowrap;line-height:1.5}
.chip.type{background:none;border:1px solid var(--line);color:var(--muted);
font-weight:500;text-transform:uppercase;font-size:.68rem;letter-spacing:.05em}
.chip.status{background:var(--chip);color:var(--fg)}
/* status colours must outrank the base rule above */
.chip.status.st-good{background:var(--good-bg);color:var(--good)}
.chip.status.st-warn{background:var(--warn-bg);color:var(--warn)}
.chip.status.st-bad{background:var(--bad-bg);color:var(--bad)}
.chip.status.st-done{background:var(--done-bg);color:var(--done)}
.chip.tag{background:var(--chip);color:var(--muted);font-weight:400}
.chip.stale{background:var(--warn-bg);color:var(--warn)}
.chip.archived{background:var(--chip);color:var(--muted);font-weight:400;
text-decoration:line-through}
.chip.docid{background:var(--chip);border:1px solid var(--line);color:var(--muted);
font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-weight:400;font-size:.72rem}
.chip.lnk{background:none;border:1px solid var(--line);color:var(--muted);cursor:pointer;
font-family:inherit;font-size:.78rem}
.chip.lnk:hover{color:var(--accent);border-color:var(--accent);text-decoration:none}
.meta{display:flex;flex-wrap:wrap;gap:.4rem;margin:.9rem 0 1.25rem;align-items:center}
.actions{display:flex;flex-wrap:wrap;gap:.5rem;margin:0 0 1.5rem}
.abtn{display:inline-flex;align-items:center;gap:.45rem;border:1px solid var(--line);
border-radius:8px;padding:.34rem .7rem;font-size:.82rem;color:var(--muted);background:var(--bg);
cursor:pointer;font-family:inherit}
.abtn:hover{background:var(--chip);color:var(--fg);text-decoration:none}
.abtn code{font-size:.78rem;color:var(--fg);background:none;border:0;padding:0}
h2.section .n{color:var(--faint);font-weight:400}
h2.section .dot{width:8px;height:8px;border-radius:99px;flex:none}
.crumbs{font-size:.84rem;color:var(--muted);margin:0 0 .9rem}
.crumbs a{color:var(--muted)}
/* the docir id is the one index a document has; chrome shows it in mono */
.bc-id{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:.78rem;
color:var(--faint)}
.banner{display:flex;gap:.7rem;align-items:flex-start;background:var(--warn-bg);
color:var(--warn);border:1px solid color-mix(in srgb,var(--warn) 30%,transparent);
border-radius:10px;padding:.8rem 1rem;margin:1.25rem 0;font-size:.92rem;line-height:1.55}
.banner b{font-weight:650}
.banner a{color:inherit;text-decoration:underline}
.banner .ic{flex:none;font-size:1rem;line-height:1.5}
.banner .also{display:block;opacity:.85}
/* ---- rail groups ----
   A label over its content, not a card around it. Four stacked filled panels
   made the rail the loudest column on the page; only the two that are read as
   a unit — the trust figures and the map — keep a border. */
.railgrp{margin:0 0 1.6rem}
.railgrp h2{margin:0 0 .5rem;font-size:.72rem;text-transform:uppercase;
letter-spacing:.07em;color:var(--muted);font-weight:600}
.railgrp ul{list-style:none;margin:0;padding:0}
.railgrp li{margin:.3rem 0;line-height:1.45}
.toc a{display:block;padding:.22rem 0 .22rem .75rem;color:var(--muted);
border-left:2px solid var(--line-soft);line-height:1.45}
.toc a:hover{color:var(--fg);text-decoration:none}
.toc a.on{color:var(--accent);border-left-color:var(--accent);font-weight:600}
.legend a{display:flex;align-items:center;gap:.45rem;color:var(--muted)}
.legend a:hover{color:var(--accent);text-decoration:none}
.legend .n{color:var(--faint);font-variant-numeric:tabular-nums}
.legend .dot{width:8px;height:8px;border-radius:99px;flex:none}
.rel .kind{display:flex;align-items:center;gap:.4rem;color:var(--faint);font-size:.72rem;
text-transform:uppercase;letter-spacing:.05em;margin:.7rem 0 .2rem}
.rel .kind:first-child{margin-top:0}
.rel a{color:var(--muted)}
.rel a:hover{color:var(--accent)}
.dead{color:var(--faint);border-bottom:1px dashed var(--faint);cursor:help}
.trust{border:1px solid var(--line);border-radius:10px;padding:.8rem .9rem;font-size:.82rem}
.trust .trow{display:flex;justify-content:space-between;gap:.8rem;margin:.25rem 0}
.trust .k{color:var(--muted)}
.trust .v{font-variant-numeric:tabular-nums;text-align:right}
.trust .stale-note{color:var(--warn);justify-content:flex-start;font-weight:600}
.trust .stale-note a{color:inherit}
.map-box{border:1px solid var(--line);border-radius:10px;padding:.7rem .9rem .6rem}
.map-box svg{width:100%;height:auto;display:block;margin:.15rem 0 .3rem}
.map-box .edge{stroke:var(--line);stroke-width:1.2}
.map-box .elbl{fill:var(--faint);font-size:7.5px;font-family:ui-monospace,Menlo,monospace;
text-transform:uppercase;letter-spacing:.06em}
.map-box .nlbl{fill:var(--muted);font-size:9.5px}
.map-box .nlbl.ctr{fill:var(--fg);font-weight:600}
.map-box .ring{fill:none;stroke:var(--accent);stroke-width:1.6}
.map-box a:hover .nlbl{fill:var(--accent)}
.map-box .full{font-size:.78rem}
/* ---- document body ---- */
.body{margin-top:1.25rem}
.body p{margin:1rem 0}
.body h1{font-size:1.35rem;margin:2rem 0 .5rem}
.body h2{font-size:1.35rem;margin:2.2rem 0 .6rem;padding-bottom:.35rem;
border-bottom:1px solid var(--line-soft);letter-spacing:-.01em;scroll-margin-top:76px}
.body h3{font-size:1.05rem;margin:1.6rem 0 .4rem}
.body ul{padding-left:1.4rem}
.body li{margin:.4rem 0}
.body code{background:var(--code);border:1px solid var(--line-soft);
padding:.08rem .35rem;border-radius:6px;font-size:.85em}
/* A cited docir id. Mono because it is an identifier, not prose, and the same
   chip whether the source wrote it bare or in a code span — the reader should
   not be able to tell which, since both mean the same document. */
.body a.docref{font-family:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
font-size:.85em;background:var(--code);border:1px solid var(--line-soft);
padding:.08rem .35rem;border-radius:6px;white-space:nowrap}
.body a.docref code{background:none;border:0;padding:0;font-size:1em;color:inherit}
.body a.docref:hover{border-color:var(--accent);text-decoration:none}
/* ---- code blocks: a titled frame, not a grey rectangle ----
   The header carries the language and the copy button. Hanging the button
   inside the <pre> meant it overlapped the first line at narrow widths and
   only appeared on hover, which no touch device has. */
.codeblk{border:1px solid var(--line);border-radius:10px;overflow:hidden;margin:1.2rem 0;
background:var(--code)}
.codeblk .hd{display:flex;align-items:center;justify-content:space-between;
padding:.4rem .9rem;font-size:.76rem;color:var(--muted);
border-bottom:1px solid var(--line-soft);background:var(--chip)}
.codeblk .hd button{border:0;background:none;cursor:pointer;font:inherit;font-size:.76rem;
color:var(--muted);padding:0}
.codeblk .hd button:hover{color:var(--accent)}
.codeblk pre{margin:0;padding:.9rem 1rem;overflow-x:auto;font-size:.84rem;line-height:1.6;
font-family:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace}
.codeblk pre code{background:none;border:0;padding:0;font-size:1em}
.sy-cmt{color:var(--sy-cmt)}.sy-kw{color:var(--sy-kw)}.sy-str{color:var(--sy-str)}
.sy-fn{color:var(--sy-fn)}.sy-flag{color:var(--sy-flag)}
.body table{margin:1rem 0;display:block;overflow-x:auto;border-collapse:collapse}
.body th,.body td{border:1px solid var(--line);padding:.4rem .6rem;text-align:left}
.body img{max-width:100%}
.body blockquote{margin:1rem 0;padding-left:1rem;border-left:3px solid var(--line);
color:var(--muted)}
.body .anchor{opacity:0;padding-left:.4rem;font-weight:400;color:var(--muted)}
.body h1:hover .anchor,.body h2:hover .anchor,.body h3:hover .anchor{opacity:1}
.pn{display:grid;grid-template-columns:1fr 1fr;gap:.75rem;margin:2.5rem 0 0;
border-top:1px solid var(--line-soft);padding-top:1.25rem}
.pn a{border:1px solid var(--line);border-radius:10px;padding:.7rem .95rem;display:block;
color:var(--fg);font-size:.9rem}
.pn a:hover{border-color:var(--accent);text-decoration:none}
.pn .lbl{display:block;color:var(--faint);font-size:.76rem;margin-bottom:.15rem}
.pn .next{text-align:right}
.foot-meta{margin-top:1.5rem;display:flex;gap:1.25rem;flex-wrap:wrap;
color:var(--faint);font-size:.82rem}
.foot-meta button{border:0;background:none;color:var(--faint);cursor:pointer;
font:inherit;padding:0}
.foot-meta button:hover{color:var(--accent)}
.foot-meta code{font-size:.78rem;background:none;border:0}
footer{margin-top:2.5rem;color:var(--faint);font-size:.82rem;
border-top:1px solid var(--line-soft);padding-top:1rem}
/* ---- palette ---- */
.scrim{position:fixed;inset:0;z-index:60;background:rgba(10,12,16,.45);
display:flex;align-items:flex-start;justify-content:center;padding:10vh 1rem 0;
backdrop-filter:blur(2px)}
.palette{width:min(37rem,100%);background:var(--bg);border:1px solid var(--line);
border-radius:12px;box-shadow:var(--shadow);overflow:hidden}
.palette input{width:100%;border:0;border-bottom:1px solid var(--line-soft);
background:none;color:var(--fg);font:inherit;font-size:1rem;padding:.9rem 1.1rem;
outline:none}
.pres{max-height:22rem;overflow-y:auto;padding:.4rem}
.pgrp{padding:.5rem .7rem .2rem;font-size:.7rem;text-transform:uppercase;
letter-spacing:.07em;color:var(--faint)}
.pit{display:flex;align-items:center;gap:.6rem;padding:.5rem .7rem;border-radius:8px;
cursor:pointer;font-size:.9rem}
.pit .pm{margin-left:auto;color:var(--faint);font-size:.76rem;white-space:nowrap}
.pit.on{background:color-mix(in srgb,var(--accent) 10%,transparent)}
.pnone{padding:1.2rem;color:var(--faint);text-align:center;font-size:.9rem}
.pftr{display:flex;gap:1rem;padding:.5rem .9rem;border-top:1px solid var(--line-soft);
color:var(--faint);font-size:.74rem}
.pftr kbd{border:1px solid var(--line);border-radius:4px;padding:0 .3rem;font-size:.7rem;
background:var(--chip)}
/* ---- hover preview (the Quartz pattern) ---- */
.preview{position:fixed;z-index:70;width:19rem;background:var(--bg);
border:1px solid var(--line);border-radius:10px;box-shadow:var(--shadow);
padding:.75rem .9rem;font-size:.82rem;pointer-events:none;line-height:1.5}
.preview .pvt{font-weight:600;margin-bottom:.2rem}
.preview .pvd{color:var(--muted)}
.preview .pvm{margin-top:.45rem;color:var(--faint);font-size:.74rem}
/* ---- responsive ---- */
/* Below the three-column width the rail stops being a column and becomes
   part of the flow — *after* the document, not before it. Stacked above, its
   four groups put up to two screens of contents/trust/map/relations between a
   reader who tapped a title and the title they tapped. The rail still
   precedes the body in source order; only the grid placement moves, so the
   guarantee that nothing important is unreachable holds at every width. */
@media(max-width:1150px){.shell{grid-template-columns:260px minmax(0,1fr)}
.rail{grid-column:2;grid-row:2;position:static;max-height:none;
padding:0 1.25rem 1rem;max-width:45rem;margin:0 auto;width:100%}
.main{grid-row:1}
.shellfoot{grid-row:3}}
@media(max-width:920px){
.shell,.shell.norail{grid-template-columns:minmax(0,1fr)}
.sidebar{display:none;position:fixed;left:0;top:56px;bottom:0;z-index:50;width:290px;
background:var(--bg);border-right:1px solid var(--line);box-shadow:var(--shadow)}
.sidebar.open{display:block}
.menubtn{display:inline-block}
.rail,.main,.shellfoot{grid-column:1}
.searchbtn{min-width:0}.searchbtn .hint{display:none}
.toplnk.queue{display:none}}
@media(max-width:"""
    + _NARROW
    + """){ul.docs li{grid-template-columns:1fr}.side{margin-top:.4rem;grid-row:auto;
grid-column:1}
.tiles{grid-template-columns:repeat(2,1fr)}}
"""
)

_FILTER_JS = """\
const rows=[...document.querySelectorAll('li[data-hay]')];
const q=document.getElementById('q'),count=document.getElementById('fcount');
const fclear=document.getElementById('fclear');
const recent=document.getElementById('recent');
const staleTgl=document.getElementById('staleTgl');
const chipsBar=document.getElementById('chipsBar');
const viewsBar=document.getElementById('views');
const noHits=document.getElementById('noHits');
const dF=document.getElementById('dfrom'), dT=document.getElementById('dto');
// The owner facet renders only when a document has an owner; the facet list
// adapts here rather than the script branching on corpus shape everywhere.
const FACETS=['type','status'].concat(document.getElementById('oopts')?['owner']:[]);
const OPTS={type:'topts',status:'sopts',owner:'oopts'};
const SUMS={type:'tsum',status:'ssum',owner:'osum'};
const D_LABEL={'7d':'last 7 days','30d':'last 30 days','90d':'last 90 days',year:'this year'};
const KNOWN={};
for(const f of FACETS)KNOWN[f]=new Set(rows.map(r=>r.dataset[f]||'').filter(Boolean));
const esc=s=>s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
// Faceted-search semantics, per the standard playbook: multi-select inside a
// facet is OR, facets combine as AND with each other and the text query, and
// each option shows the count it would yield. The chips above the list are
// the canonical display of applied state; a `-` value is an exclusion.
const state={q:'',stale:null,dmode:'',dfrom:'',dto:'',
  type:{inc:new Set(),exc:new Set()},
  status:{inc:new Set(),exc:new Set()},
  owner:{inc:new Set(),exc:new Set()}};
const chipOrder=[]; // insertion order — "remove last filter" pops this

const iso=d=>d.toISOString().slice(0,10);
// Preset windows are *rolling*: a copied "last 30 days" link shows the 30
// days before whenever it is opened. An absolute view is what the custom
// range is for. ISO dates compare correctly as strings — no Date parsing on
// the compare path, no timezone to get wrong.
function dateLo(){
  if(state.dmode==='custom') return state.dfrom;
  if(state.dmode==='year') return new Date().getFullYear()+'-01-01';
  const days={'7d':7,'30d':30,'90d':90}[state.dmode];
  if(!days) return '';
  const d=new Date(); d.setDate(d.getDate()-days); return iso(d);
}
function dateHi(){ return state.dmode==='custom'?state.dto:''; }

function setHit(sel,val){ return !sel.exc.has(val)&&(!sel.inc.size||sel.inc.has(val)); }
// One predicate with a `skip` so each facet's counts can be computed under
// every *other* active filter — the number beside an option is what
// selecting it would actually show.
function rowHit(r,skip){
  const t=state.q, lo=dateLo(), hi=dateHi(), u=r.dataset.updated;
  return (skip==='q'||!t||r.dataset.hay.includes(t))
    &&(skip==='type'||setHit(state.type,r.dataset.type))
    &&(skip==='status'||setHit(state.status,r.dataset.status))
    &&(skip==='owner'||setHit(state.owner,r.dataset.owner||''))
    &&(skip==='stale'||state.stale===null||((r.dataset.stale==='1')===state.stale))
    &&(skip==='date'||((!lo||u>=lo)&&(!hi||u<=hi)));
}

// -- state mutation: one door per fact, so chips, boxes and URL cannot drift --
function addValue(facet,value,neg){
  const set=neg?state[facet].exc:state[facet].inc;
  if(set.has(value))return;
  set.add(value); chipOrder.push({facet,value,neg}); syncBoxes(facet);
}
function dropValue(facet,value,neg){
  (neg?state[facet].exc:state[facet].inc).delete(value);
  const i=chipOrder.findIndex(c=>c.facet===facet&&c.value===value&&c.neg===neg);
  if(i>=0)chipOrder.splice(i,1);
  syncBoxes(facet);
}
function setStale(v){ // true | false (from -is:stale) | null
  state.stale=v;
  const i=chipOrder.findIndex(c=>c.facet==='stale');
  if(i>=0)chipOrder.splice(i,1);
  if(v!==null)chipOrder.push({facet:'stale',neg:v===false});
  if(staleTgl)staleTgl.classList.toggle('on',v===true);
}
function setDate(mode,from,to){
  state.dmode=mode; state.dfrom=from||''; state.dto=to||'';
  const i=chipOrder.findIndex(c=>c.facet==='updated');
  if(i>=0)chipOrder.splice(i,1);
  if(mode)chipOrder.push({facet:'updated'});
  const rb=document.querySelector(`input[name=dpre][value="${mode}"]`)||
    document.querySelector('input[name=dpre][value=""]');
  rb.checked=true; dF.value=state.dfrom; dT.value=state.dto;
}
function syncBoxes(f){
  for(const cb of document.querySelectorAll('#'+OPTS[f]+' input'))
    cb.checked=state[f].inc.has(cb.value);
}
function clearAll(){
  state.q=''; q.value='';
  for(const f of FACETS){state[f].inc.clear();state[f].exc.clear();syncBoxes(f);}
  state.stale=null; if(staleTgl)staleTgl.classList.remove('on');
  setDate('');
  chipOrder.length=0;
}

// -- applied filters as chips: visible, individually removable, in add order --
function renderChips(){
  chipsBar.innerHTML=chipOrder.map((c,i)=>{
    let lbl;
    if(c.facet==='stale') lbl=(c.neg?'not ':'')+'stale';
    else if(c.facet==='updated') lbl='updated: '+(state.dmode==='custom'
      ?(state.dfrom||'\\u2026')+' \\u2192 '+(state.dto||'\\u2026')
      :(D_LABEL[state.dmode]||state.dmode));
    else lbl=(c.neg?'not ':'')+c.facet+': '+esc(c.value);
    return `<span class="fchip${c.neg?' neg':''}">${lbl}`+
      `<button class="x" data-chip="${i}" aria-label="remove filter">\\u00d7</button></span>`;
  }).join('');
  chipsBar.hidden=!chipOrder.length;
}
function removeChipAt(i){
  const c=chipOrder[i]; if(!c)return;
  if(c.facet==='stale')setStale(null);
  else if(c.facet==='updated')setDate('');
  else dropValue(c.facet,c.value,c.neg);
}
chipsBar.addEventListener('click',e=>{
  const b=e.target.closest('[data-chip]'); if(!b)return;
  removeChipAt(+b.dataset.chip); apply(true);
});

// -- tracker-style tokens typed into the box become chips. Only a token whose
// value the corpus actually has converts; anything else stays free text. --
const TOKEN=/(^|\\s)(-?)(type|status|owner|is|updated):([\\w][\\w.-]*)(?=\\s|$)/gi;
function extractTokens(final){
  let text=q.value, changed=false, m; const found=[];
  TOKEN.lastIndex=0;
  while((m=TOKEN.exec(text))){
    const end=m.index+m[0].length;
    if(!final&&end===text.length&&!/\\s$/.test(text))continue; // still typing
    found.push({neg:m[2]==='-',key:m[3].toLowerCase(),val:m[4].toLowerCase(),str:m[0]});
  }
  for(const t of found){
    let ok=false;
    if(KNOWN[t.key]){ if(KNOWN[t.key].has(t.val)){addValue(t.key,t.val,t.neg);ok=true;} }
    else if(t.key==='is'&&t.val==='stale'){setStale(!t.neg);ok=true;}
    else if(t.key==='updated'&&D_LABEL[t.val]){setDate(t.val);ok=true;}
    if(ok){text=text.replace(t.str,' ');changed=true;}
  }
  if(changed)q.value=text.replace(/\\s{2,}/g,' ').replace(/^\\s+/,'');
  return changed;
}

function refreshCounts(){
  for(const f of FACETS){
    for(const lab of document.querySelectorAll('#'+OPTS[f]+' label')){
      const v=lab.dataset.fv;
      const n=rows.filter(r=>(r.dataset[f]||'')===v&&rowHit(r,f)).length;
      lab.querySelector('.n').textContent=n;
      // A zero-count option dims rather than vanishing: an option that
      // disappears reads as a bug, and a selection is never silently dropped
      // — its chip stays visible as the cause of an empty list.
      const ghost=n===0&&!state[f].inc.has(v);
      lab.classList.toggle('ghost',ghost);
      lab.querySelector('input').disabled=ghost;
    }
  }
}
// The summary is the applied-state display: a closed facet must still say
// how much of it is switched on.
function refreshSummaries(){
  for(const f of FACETS){
    const n=state[f].inc.size+state[f].exc.size;
    document.getElementById(SUMS[f]).textContent=n?' \\u00b7 '+n:'';
  }
  const dl=state.dmode==='custom'?'range':state.dmode;
  document.getElementById('dsum').textContent=dl?' \\u00b7 '+dl:'';
}
function serialize(){
  const p=new URLSearchParams();
  if(state.q)p.set('q',state.q);
  for(const f of FACETS){
    const vals=[...state[f].inc].sort().concat([...state[f].exc].sort().map(v=>'-'+v));
    if(vals.length)p.set(f,vals.join(','));
  }
  if(state.stale!==null)p.set('is',(state.stale?'':'-')+'stale');
  if(state.dmode==='custom'){
    if(state.dfrom)p.set('from',state.dfrom);
    if(state.dto)p.set('to',state.dto);
  } else if(state.dmode)p.set('updated',state.dmode);
  return p.toString();
}
// Arriving state — the URL on load, Back/Forward, a preset view — funnels
// through one reader. A value naming an option the corpus does not have is
// dropped rather than filtering everything to zero.
function applyParams(p){
  q.value=p.get('q')||''; state.q=q.value.toLowerCase().trim();
  for(const f of FACETS)
    for(const v of (p.get(f)||'').split(',')){
      if(!v)continue;
      const neg=v.startsWith('-'), val=neg?v.slice(1):v;
      if(KNOWN[f].has(val))addValue(f,val,neg);
    }
  const is0=p.get('is')||'';
  if(is0==='stale')setStale(true); else if(is0==='-stale')setStale(false);
  const up=p.get('updated')||'';
  if(D_LABEL[up])setDate(up);
  // Only a well-formed date survives the URL. These variables feed string
  // comparisons directly — "?from=garbage" compares above every ISO date and
  // would silently filter the page to nothing.
  const isoRe=/^\\d{4}-\\d{2}-\\d{2}$/;
  const f0=p.get('from')||'', t0=p.get('to')||'';
  if(isoRe.test(f0)||isoRe.test(t0))
    setDate('custom',isoRe.test(f0)?f0:'',isoRe.test(t0)?t0:'');
}

function apply(push){
  const on=!!(state.q||chipOrder.length);
  let shown=0;
  for(const r of rows){const hit=rowHit(r,'');r.hidden=!hit;if(hit)shown++;}
  for(const s of document.querySelectorAll('section[data-type]')){
    s.hidden=![...s.querySelectorAll('li[data-hay]')].some(r=>!r.hidden);
  }
  // The recent strip is a browsing shortcut; while any filter is active,
  // filtering has replaced browsing and the strip would only duplicate rows.
  if(recent) recent.hidden=on;
  noHits.hidden=shown>0;
  document.getElementById('undoLast').hidden=!chipOrder.length;
  fclear.hidden=!on;
  count.textContent=on?shown+' shown':'';
  refreshCounts(); refreshSummaries(); renderChips();
  const qs=serialize();
  if(viewsBar)for(const b of viewsBar.querySelectorAll('[data-sig]'))
    b.classList.toggle('on',b.dataset.sig===qs);
  // The URL carries the whole filter state, so the current view is a
  // copyable link. Every facet change is a history entry — users perceive
  // each one as a view, and Back must undo it — while typing only replaces:
  // a keystroke is not a step.
  const next=qs?'?'+qs:'';
  if(next!==location.search)
    (push?history.pushState:history.replaceState).call(history,null,'',next||location.pathname);
}

// -- wiring --
for(const f of FACETS)
  document.getElementById(OPTS[f]).addEventListener('change',e=>{
    e.target.checked?addValue(f,e.target.value,false):dropValue(f,e.target.value,false);
    apply(true);
  });
for(const rb of document.querySelectorAll('input[name=dpre]'))
  rb.onchange=()=>{setDate(rb.value,dF.value,dT.value);apply(true);};
// Typing a date IS choosing the custom range — demanding the radio first
// would make the visible inputs silently do nothing.
dF.oninput=()=>{setDate('custom',dF.value,dT.value);apply(true);};
dT.oninput=()=>{setDate('custom',dF.value,dT.value);apply(true);};
q.addEventListener('input',()=>{
  const converted=extractTokens(false);
  state.q=q.value.toLowerCase().trim();
  apply(converted);
});
q.addEventListener('keydown',e=>{
  if(e.key==='Enter'){extractTokens(true);state.q=q.value.toLowerCase().trim();apply(true);}
});
if(staleTgl)staleTgl.onclick=()=>{setStale(state.stale===true?null:true);apply(true);};
fclear.onclick=()=>{clearAll();apply(true);};
document.getElementById('clearAllBtn').onclick=()=>{clearAll();apply(true);};
document.getElementById('undoLast').onclick=()=>{removeChipAt(chipOrder.length-1);apply(true);};
if(viewsBar)viewsBar.addEventListener('click',e=>{
  const b=e.target.closest('[data-sig]'); if(!b)return;
  clearAll(); applyParams(new URLSearchParams(b.dataset.sig)); apply(true);
});
// A facet dropdown closes when the pointer goes elsewhere — the standard
// popover contract; without it three open panels shingle over the list.
addEventListener('pointerdown',e=>{
  for(const d of document.querySelectorAll('details.facet[open]'))
    if(!d.contains(e.target)) d.open=false;
});
// `/` focuses the filter, `f` opens the first facet, Shift+F clears — the
// shortcuts readers bring from issue trackers.
addEventListener('keydown',e=>{
  if(e.metaKey||e.ctrlKey||e.altKey)return;
  if(/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName))return;
  if(e.key==='/'){e.preventDefault();q.focus();}
  else if(e.key==='F'&&e.shiftKey){clearAll();apply(true);}
  else if(e.key==='f'){e.preventDefault();
    const d=document.querySelector('details.facet');
    if(d){d.open=true;const cb=d.querySelector('input:not([disabled])');cb&&cb.focus();}}
});
applyParams(new URLSearchParams(location.search));
apply(false);
// Back/Forward walk the filter history apply() wrote.
addEventListener('popstate',()=>{
  clearAll(); applyParams(new URLSearchParams(location.search)); apply(false);
});
"""


def render_site(
    site: Site, *, title: str, version: str, branding: Branding = DOCIR_BRANDING
) -> dict[str, str]:
    """Render the whole site as ``relative path -> file contents``.

    One page per document plus its markdown source, the index, and the graph —
    the corpus drawn as an interactive map. Returning content rather than
    writing it keeps this layer free of the filesystem, so a test can assert on
    the HTML without a temp directory and the writer has exactly one job.
    """
    by_id = {document.id: document for document in site.documents}
    # Previous/next inside the document's own type, in the listing's order —
    # a reader flipping through decisions gets the next decision, not an
    # id-adjacent runbook.
    neighbors: dict[str, tuple[SiteDocument | None, SiteDocument | None]] = {}
    for _, documents in site.groups:
        for index, document in enumerate(documents):
            neighbors[document.id] = (
                documents[index - 1] if index > 0 else None,
                documents[index + 1] if index + 1 < len(documents) else None,
            )
    pages = {
        "index.html": _render_index(site, title=title, version=version, branding=branding),
        "graph.html": render_graph_page(site, title=title, branding=branding),
    }
    for document in site.documents:
        pages[page_name(document.id)] = _render_document(
            document,
            site=site,
            title=title,
            version=version,
            by_id=by_id,
            neighbors=neighbors[document.id],
            branding=branding,
        )
        pages[source_name(document.id)] = document.body
    return pages


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


# -- index ------------------------------------------------------------------


def _render_index(site: Site, *, title: str, version: str, branding: Branding) -> str:
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
<script>{_FILTER_JS}</script>"""
    return _page(
        title,
        body,
        version,
        site_title=title,
        sidebar=_render_sidebar(site, active="index"),
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
        f'<li><a href="?type={html.escape(name)}">{_type_dot(name)}'
        f"{html.escape(_type_label(name, plural=True))}"
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


#: How many documents the "recently updated" strip shows. Below roughly twice
#: this, the strip would just repeat the listing underneath it.
_RECENT_COUNT = 5


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
<h2 class="section">{_type_dot(type_name)}\
{html.escape(_type_label(type_name, plural=True))} <span class="n">{len(documents)}</span></h2>
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
  <div class="side">{_state_chips(document)}{_status_chip(document)}\
<time datetime="{html.escape(document.updated)}">{html.escape(document.updated)}</time></div>
</li>"""


# -- document ---------------------------------------------------------------


def _render_document(
    document: SiteDocument,
    *,
    site: Site,
    title: str,
    version: str,
    by_id: Mapping[str, SiteDocument],
    neighbors: tuple[SiteDocument | None, SiteDocument | None],
    branding: Branding,
) -> str:
    # Every published document except this one: a body that names its own id
    # would otherwise get a link to the page it is already on, which reads as a
    # live cross-reference and goes nowhere.
    body_html, headings = render_body(
        document.body,
        drop_title=document.title,
        known_ids=by_id.keys() - {document.id},
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
{html.escape(_type_label(document.type, plural=True))}</a> / \
<span class="bc-id">{escaped_id}</span></p>
<header class="top">
  <h1>{html.escape(document.title)}</h1>
</header>
<p class="standfirst">{html.escape(document.description)}</p>
<div class="meta">{_id_chip(document)}{_type_chip(document)}{_status_chip(document)}\
{_tag_chips(document)}{_state_chips(document)}</div>
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
    return _page(
        f"{document.title} — {title}",
        body,
        version,
        site_title=title,
        sidebar=_render_sidebar(site, active=document.id),
        branding=branding,
        rail=rail,
        stale_count=site.stale_count,
    )


def _render_sidebar(site: Site, *, active: str) -> str:
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
            f"{_type_dot(type_name)}{html.escape(_type_label(type_name, plural=True))}"
            f' <span class="n">{len(documents)}</span>'
            f'<span class="tw" aria-hidden="true">▸</span></summary>'
            f"<ul>{''.join(items)}</ul></details>"
        )
    return "".join(groups)


#: Type names that are mass nouns: "3 architecture documents", never
#: "3 architectures". The naive +s rule is right for the countable bundled
#: types (decisions, issues, runbooks) and wrong for these two, and a heading
#: reading "Architectures" is the kind of blemish that makes a generated site
#: look generated.
_UNCOUNTABLE_TYPES = frozenset({"architecture", "reference", "research", "documentation"})


def _type_label(type_name: str, *, plural: bool = False) -> str:
    """A type as a heading reads it: `release_note` -> `Release notes`.

    The schema's identifiers are snake_case singulars because they are keys;
    a nav group listing eighteen of them is prose. Pluralisation is the naive
    English rule minus the mass nouns above — harmless for a custom type,
    where a wrong plural is cosmetic and an unreadable key is not. Facet
    options deliberately keep the raw key: they have to match the
    `type:release_note` token the same filter box accepts.
    """
    words = type_name.replace("_", " ")
    label = words[:1].upper() + words[1:] if words else words
    if plural and not label.endswith("s") and type_name not in _UNCOUNTABLE_TYPES:
        label += "s"
    return label


def _type_dot(type_name: str) -> str:
    """A colour swatch for a type — always beside the type's name.

    The name is the encoding; the colour is reinforcement. Types outside the
    token palette fall back to the muted grey rather than minting a hue the
    graph would not agree with.
    """
    return (
        f'<span class="dot" '
        f'style="background:var(--t-{html.escape(type_name)},var(--muted))"></span>'
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
        ("Verified", document.verified or "never"),
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


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


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


# -- chips ------------------------------------------------------------------
#
# A type, a status and a tag are three different kinds of fact and were three
# identical grey pills. Each now has its own treatment, and a `title` for the
# reader who hovers rather than guesses.


def _id_chip(document: SiteDocument) -> str:
    # The docir id is the one index a document has; it appears in mono
    # wherever chrome needs identity, and matches the copyable CLI command.
    return f'<span class="chip docid" title="document id">{html.escape(document.id)}</span>'


def _type_chip(document: SiteDocument) -> str:
    return f'<span class="chip type" title="document type">{html.escape(document.type)}</span>'


def _status_chip(document: SiteDocument) -> str:
    semantic = _STATUS_CLASS.get(document.status)
    cls = f"chip status {semantic}" if semantic else "chip status"
    return f'<span class="{cls}" title="status">{html.escape(document.status)}</span>'


def _tag_chips(document: SiteDocument) -> str:
    # The `#` is the label. A word of prose per chip would be noise; the sigil
    # is read instantly and is what a tag looks like everywhere else.
    return "".join(
        f'<span class="chip tag" title="tag">#{html.escape(tag)}</span>' for tag in document.tags
    )


def _state_chips(document: SiteDocument) -> str:
    chips = ""
    if document.stale:
        chips += '<span class="chip stale" title="past its review cadence">⚠ stale</span>'
    if document.archived:
        chips += '<span class="chip archived" title="archived">archived</span>'
    return chips


# -- markdown ---------------------------------------------------------------

_HEADING_CLOSE = re.compile(r"</h([1-6])>")
_ANCHOR_GLYPH = "¶"


def render_body(
    text: str,
    *,
    drop_title: str = "",
    known_ids: Collection[str] = (),
) -> tuple[str, list[tuple[int, str, str]]]:
    """Render a body to HTML, id its headings, and report them.

    Ids come from the token stream rather than a regex over rendered HTML: the
    tokens already carry the level and the text, and rewriting generated markup
    to work out what it meant is how a renderer acquires a second parser.

    ``drop_title`` removes a leading level-1 heading that repeats the document
    title — docir's own convention restates it as the body's first line, which
    published the title twice with the second one larger.

    ``known_ids`` are the documents this site publishes; a bare docir id in the
    prose that names one of them becomes a link to its page.
    """
    parser = MarkdownIt("commonmark", {"linkify": False}).enable("table")
    # Both code token types, so an indented block is framed like a fenced one.
    parser.add_render_rule("fence", _render_fence)
    parser.add_render_rule("code_block", _render_fence)
    tokens = _drop_leading_title(parser.parse(text), drop_title)
    _linkify_doc_ids(tokens, frozenset(known_ids))

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


#: Shape of a *candidate* docir id in prose. Deliberately loose — it only has to
#: bracket something worth looking up, and every match is then checked against
#: the ids the site actually publishes, so a false positive cannot survive. The
#: alternative, a real id grammar, would have to be kept in step with whatever
#: `id_style` mints (12 hex chars today, four digits in a sequential store) and
#: would silently stop linking the day a third style is added.
_DOC_ID_SHAPE = re.compile(r"\b[a-z][a-z0-9]*-[a-z0-9]{4,}\b")


def _linkify_doc_ids(tokens: list, known: frozenset[str]) -> None:
    """Turn bare docir ids in the prose into links to their pages, in place.

    A body refers to another document by its id, which is the only identifier a
    document has — sequence labels inside titles are title text. Written plain
    that id publishes as an unlinked string of hex, so the one canonical way to
    cite a document was also the one that gave the reader nothing to follow.

    Operates on the token stream, not the rendered HTML, which is what keeps it
    from linking ids inside fenced code, and — via ``depth`` — from nesting an
    anchor inside a link whose text happens to be an id. A ``code_inline`` whose
    whole content is an id is wrapped rather than rewritten, so the existing
    ```id``` spelling keeps its mono styling and gains the link.
    """
    if not known:
        return
    for token in tokens:
        if token.type != "inline" or not token.children:
            continue
        children, depth, changed = [], 0, False
        for child in token.children:
            if child.type == "link_open":
                depth += 1
            elif child.type == "link_close":
                depth -= 1
            if depth > 0:
                children.append(child)
                continue
            if child.type == "code_inline" and child.content.strip() in known:
                children.extend(_doc_link(child.content.strip(), child))
                changed = True
            elif child.type == "text" and (parts := _split_ids(child.content, known)):
                children.extend(parts)
                changed = True
            else:
                children.append(child)
        if changed:
            token.children = children


def _split_ids(text: str, known: frozenset[str]) -> list | None:
    """``text`` as tokens with every known id linked, or ``None`` if none is."""
    out, cursor = [], 0
    for match in _DOC_ID_SHAPE.finditer(text):
        if match.group() not in known:
            continue
        if match.start() > cursor:
            out.append(_text_token(text[cursor : match.start()]))
        out.extend(_doc_link(match.group(), _code_token(match.group())))
        cursor = match.end()
    if not out:
        return None
    if cursor < len(text):
        out.append(_text_token(text[cursor:]))
    return out


def _doc_link(doc_id: str, inner: Token) -> list[Token]:
    open_token = Token("link_open", "a", 1)
    open_token.attrs = {"class": "docref", "href": page_name(doc_id)}
    return [open_token, inner, Token("link_close", "a", -1)]


def _text_token(content: str) -> Token:
    token = Token("text", "", 0)
    token.content = content
    return token


def _code_token(content: str) -> Token:
    token = Token("code_inline", "code", 0)
    token.content = content
    return token


def _render_fence(_renderer: object, tokens: list, index: int, *_: object) -> str:
    """A code block as a titled frame: language, copy button, coloured body.

    Replaces markdown-it's own `fence`/`code_block` rules rather than
    rewriting their output, because the token still has the info string and
    the raw source — after rendering, the language is gone and the source is
    HTML that a second pass would have to un-escape to colour. Registered via
    ``add_render_rule``, which binds the renderer as the first argument.
    """
    token = tokens[index]
    info = getattr(token, "info", "") or ""
    return (
        '<div class="codeblk"><div class="hd">'
        f"<span>{html.escape(language_label(info))}</span>"
        '<button type="button">Copy</button></div>'
        f"<pre><code>{highlight(token.content, info)}</code></pre></div>"
    )


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


# The theme toggle is shared with the graph page (`theme.THEME_TOGGLE_JS`):
# every page of the site offers the same three-state control, in the same
# corner, writing the same `localStorage` key.
_SHELL_JS = (
    THEME_TOGGLE_JS
    + """\
// -- sidebar drawer on narrow screens --
document.getElementById('menuBtn').onclick=()=>
  document.getElementById('sidebar').classList.toggle('open');

// -- the palette indexes the sidebar links: one copy of the corpus per page,
// so the two cannot disagree and the page still needs no fetch --
const palScrim=document.getElementById('palScrim'),palIn=document.getElementById('palIn'),
      palRes=document.getElementById('palRes');
const palEsc=s=>s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const palDocs=[...document.querySelectorAll('.sidebar a[data-doc]')].map(a=>({
  t:a.textContent,h:a.getAttribute('href'),ty:a.dataset.ty,st:a.dataset.st}));
// Actions are the palette's second half: the places a document page cannot
// reach with a link, plus the theme, which otherwise needs the mouse. The
// queue entry reads its href off the top-bar link rather than repeating it,
// so a page with nothing stale carries neither the action nor the URL.
const palQueue=document.querySelector('.toplnk.queue');
const palActs=[{t:'All documents',h:'index.html'},{t:'Open the graph',h:'graph.html'}]
  .concat(palQueue?[{t:'Open the review queue',h:palQueue.getAttribute('href')}]:[])
  .concat([{t:'Toggle theme',theme:1}]);
let palSel=0,palFlat=[];
function palRender(qs){
  qs=qs.toLowerCase().trim();
  const ds=palDocs.filter(d=>!qs||d.t.toLowerCase().includes(qs)||d.ty.includes(qs)||
    d.st.includes(qs)).slice(0,12);
  const as=palActs.filter(a=>!qs||a.t.toLowerCase().includes(qs));
  palFlat=[...ds,...as];palSel=0;
  let h='';
  if(ds.length)h+='<div class="pgrp">documents</div>'+ds.map((d,i)=>{
    const dot=d.ty?`<span class="dot" \
style="background:var(--t-${palEsc(d.ty)},var(--muted))"></span>`:'';
    return `<div class="pit${i===0?' on':''}" data-i="${i}">${dot}${palEsc(d.t)}`+
      `<span class="pm">${palEsc(d.ty)} \\u00b7 ${palEsc(d.st)}</span></div>`;}).join('');
  if(as.length)h+='<div class="pgrp">actions</div>'+as.map((a,i)=>
    `<div class="pit" data-i="${ds.length+i}">\\u2192 ${a.t}</div>`).join('');
  palRes.innerHTML=h||'<div class="pnone">Nothing matches.</div>';
}
function palOpen(){palScrim.hidden=false;palIn.value='';palRender('');palIn.focus();}
function palClose(){palScrim.hidden=true;}
function palPaint(){[...palRes.querySelectorAll('.pit')].forEach(el=>
  el.classList.toggle('on',+el.dataset.i===palSel));
  const on=palRes.querySelector('.pit.on');on&&on.scrollIntoView({block:'nearest'});}
function palGo(){const it=palFlat[palSel];if(!it)return;
  palClose();if(it.theme)tBtn.onclick();else location.href=it.h;}
document.getElementById('openPal').onclick=palOpen;
palIn.addEventListener('input',()=>palRender(palIn.value));
palRes.addEventListener('click',e=>{const it=e.target.closest('.pit');
  if(it){palSel=+it.dataset.i;palGo();}});
palScrim.addEventListener('click',e=>{if(e.target===palScrim)palClose();});
addEventListener('keydown',e=>{
  if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){
    e.preventDefault();palScrim.hidden?palOpen():palClose();return;}
  if(!palScrim.hidden){
    if(e.key==='Escape')palClose();
    else if(e.key==='ArrowDown'){e.preventDefault();
      palSel=Math.min(palSel+1,palFlat.length-1);palPaint();}
    else if(e.key==='ArrowUp'){e.preventDefault();palSel=Math.max(palSel-1,0);palPaint();}
    else if(e.key==='Enter')palGo();
    return;}
  // Pages without the index filter give `/` to the palette instead.
  if(e.key==='/'&&!document.getElementById('q')&&
     !/INPUT|TEXTAREA/.test(document.activeElement.tagName)){e.preventDefault();palOpen();}
});

// -- copy-to-clipboard chips: the CLI command is the sanctioned edit path --
document.addEventListener('click',e=>{
  const c=e.target.closest('[data-copy]');if(!c)return;
  navigator.clipboard&&navigator.clipboard.writeText(c.dataset.copy).catch(()=>{});
  const old=c.textContent;c.textContent='copied \\u2713';setTimeout(()=>c.textContent=old,900);});

// -- hover previews on relation links: the target's summary without the
// click, from data the renderer already resolved --
const pv=document.createElement('div');pv.className='preview';pv.hidden=true;
document.body.appendChild(pv);
document.addEventListener('mouseover',e=>{
  const a=e.target.closest('[data-pt]');if(!a)return;
  pv.innerHTML=`<div class="pvt">${palEsc(a.dataset.pt)}</div>`+
    `<div class="pvd">${palEsc(a.dataset.pd)}</div>`+
    `<div class="pvm">${palEsc(a.dataset.pm)}</div>`;
  pv.hidden=false;
  const r=a.getBoundingClientRect();
  pv.style.left=Math.max(8,Math.min(r.left,innerWidth-336))+'px';
  pv.style.top=(r.bottom+240>innerHeight?r.top-pv.offsetHeight-8:r.bottom+8)+'px';});
document.addEventListener('mouseout',e=>{if(e.target.closest('[data-pt]'))pv.hidden=true;});

// -- the copy button in each code block's header. It reads the sibling <pre>,
// so it is never inside what it copies — the failure the old floating button
// had to capture its text up-front to avoid. --
document.querySelectorAll('.codeblk .hd button').forEach(b=>{
  b.onclick=()=>{
    const pre=b.closest('.codeblk').querySelector('pre');
    navigator.clipboard&&navigator.clipboard.writeText(pre.innerText).catch(()=>{});
    b.textContent='Copied \\u2713';setTimeout(()=>b.textContent='Copy',900);};});

// -- scroll-spy for the rail contents --
const spyLinks=[...document.querySelectorAll('.rail .toc a[href^="#"]')];
if(spyLinks.length&&'IntersectionObserver' in window){
  const spyBy={};spyLinks.forEach(a=>spyBy[a.getAttribute('href').slice(1)]=a);
  const io=new IntersectionObserver(es=>es.forEach(en=>{
    if(en.isIntersecting){spyLinks.forEach(a=>a.classList.remove('on'));
      const a=spyBy[en.target.id];a&&a.classList.add('on');}}),
    {rootMargin:'-15% 0px -75% 0px'});
  for(const id in spyBy){const h=document.getElementById(id);h&&io.observe(h);}
}"""
)


def _page(
    title: str,
    body: str,
    version: str,
    *,
    site_title: str,
    sidebar: str,
    branding: Branding,
    rail: str = "",
    stale_count: int = 0,
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
<style>{_STYLES}</style>
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
<script>{_SHELL_JS}</script>
</body></html>
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
