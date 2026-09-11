"""The stylesheet and the client-side scripts, inlined into every page.

**Everything is inlined** — the CSS, the filter script, the mark, the favicon. A
published site has to work from ``file://`` and from a corporate Pages host with
no CDN reachable, and an asset pipeline for a few hundred lines of CSS would be
a build step to maintain rather than a feature.

**Class names here are scoped**, and the reason is a defect rather than taste. A
bare ``.sub`` utility, left behind when the landing's stats line was renamed,
captured ``.brand .sub`` and shrank the wordmark's tail on the pages but not on
the graph, whose stylesheet has no such rule. One brand, two sizes.

Two kinds of thing, kept together because they ship the same way: ``STYLES`` is
~380 lines that change for branding and layout, and ``FILTER_JS``/``SHELL_JS``
are ~400 that change for behaviour — the facet filtering, the search palette,
the keyboard navigation, the sort keys.
"""

from __future__ import annotations

from docir.modules.publishing.infra import diagrams
from docir.modules.publishing.infra.theme import CSS_TOKENS, THEME_TOGGLE_JS

#: Below this width the index collapses to one column. Taken from the
#: measurement that prompted it: the old table needed 426px at a 390px viewport.
_NARROW = "40rem"


STYLES = (
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
/* A `[[...]]` prose link, which resolves to a document and renders as its
   *title*. Not a docref chip: an id is an identifier and reads as code, while
   a title is prose and belongs in the sentence it was written into. The dotted
   underline is what distinguishes it from an outbound link without taking it
   out of the paragraph. */
.body a.wikiref{text-decoration:underline;text-decoration-style:dotted;
text-underline-offset:.18em}
.body a.wikiref:hover{text-decoration-style:solid}
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
    + diagrams.DIAGRAM_CSS
)


FILTER_JS = """\
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


# The theme toggle is shared with the graph page (`theme.THEME_TOGGLE_JS`):
# every page of the site offers the same three-state control, in the same
# corner, writing the same `localStorage` key.
SHELL_JS = (
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
