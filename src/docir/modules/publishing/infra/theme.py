"""The site's colour tokens — one place, imported by every page renderer.

Split out of ``rendering.py`` so the graph page can share the exact same
palette without a circular import (``rendering`` composes the site and so
imports ``graph``; ``graph`` must not import ``rendering`` back). A page that
declared its own near-identical tokens would drift the first time someone
tuned a colour in only one of them.

The dark block appears twice on purpose. ``prefers-color-scheme`` covers the
reader who never touches the theme toggle; ``:root[data-theme="dark"]`` covers
the one who chose dark on a light OS; and the ``:not([data-theme="light"])``
guard lets an explicit light choice beat OS-dark. All three have to agree, so
the dark values are one Python constant interpolated into both scopes.

``--shadow`` is a token rather than a literal for the same reason the dark
block is: the light shadow (a soft grey) is invisible over the dark surface,
so every popover — the facet menus, the palette, the hover preview — floated
with no separation from the page behind it until each one was given the
theme's own value. One token, every consumer.

The ``--sy-*`` set is the code-block syntax theme: comment, keyword, string,
function/command, flag. Five roles is the whole vocabulary the highlighter
emits (``infra/highlight.py``), chosen so a snippet reads as structure at a
glance without a colour per token type nobody can learn.

The ``--t-*`` type colours are the categorical dimension for site chrome
(sidebar dots, the local relation map). The set and its display order were
validated for colour-vision-deficiency separation in both themes (dataviz
palette check, 2026-08-04); two light-mode steps ride the low-contrast band,
which is why a type dot never appears without its type name beside it. The
graph page still carries its own node palette — swapping that is a separate,
deliberate change because the map uses colour as the only at-rest encoding.
"""

from __future__ import annotations

_DARK_VALUES = """\
--bg:#0d1117;--fg:#e6edf3;--muted:#9198a1;--faint:#6e7783;
--line:#30363d;--line-soft:#21262d;--accent:#58a6ff;--chip:#161b22;
--warn:#d29922;--warn-bg:rgba(210,153,34,.15);
--code:#161b22;--panel:#11151c;
--shadow:0 1px 3px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.4);
--good:#3fb950;--good-bg:rgba(63,185,80,.15);--bad:#f85149;--bad-bg:rgba(248,81,73,.15);
--done:#a371f7;--done-bg:rgba(163,113,247,.15);
--sy-cmt:#9198a1;--sy-kw:#ff7b72;--sy-str:#a5d6ff;--sy-fn:#d2a8ff;--sy-flag:#ffa657;
--t-decision:#3987e5;--t-issue:#d95926;--t-reference:#199e70;
--t-architecture:#9085e9;--t-runbook:#d55181;--t-release_note:#8b949e;
color-scheme:dark"""

CSS_TOKENS = (
    """\
:root{--bg:#ffffff;--fg:#1f2328;--muted:#59636e;--faint:#818b98;
--line:#d1d9e0;--line-soft:#e7ebef;--accent:#0969da;--chip:#f6f8fa;
--warn:#7d4e00;--warn-bg:#fff8c5;
--code:#f6f8fa;--panel:#fafbfc;
--shadow:0 1px 3px rgba(31,35,40,.08),0 8px 24px rgba(31,35,40,.10);
--good:#116329;--good-bg:#dafbe1;--bad:#a40e26;--bad-bg:#ffebe9;
--done:#6639ba;--done-bg:#fbefff;
--sy-cmt:#59636e;--sy-kw:#cf222e;--sy-str:#0a3069;--sy-fn:#8250df;--sy-flag:#953800;
--t-decision:#2a78d6;--t-issue:#eb6834;--t-reference:#1baf7a;
--t-architecture:#4a3aa7;--t-runbook:#e87ba4;--t-release_note:#5c6470;
color-scheme:light}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){"""
    + _DARK_VALUES
    + """}}
:root[data-theme="dark"]{"""
    + _DARK_VALUES
    + """}
"""
)

#: Restores a chosen theme before the stylesheet parses, so the page paints
#: in the right colours on load. Lives beside the tokens because every page —
#: the shell pages *and* the graph — must honour the same choice; the graph
#: skipping it would flip the reader's theme at the one navigation the site
#: most encourages. `auto` is the absence of the attribute: the media query
#: owns it.
THEME_SCRIPT = """\
(function(){var t=localStorage.getItem('docir-theme');
if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;})();"""

#: The toggle behind ``#themeBtn``: three states, cycled, persisted. Shared
#: rather than written per page because the graph page went without one — the
#: reader could change the theme on every page of the site except the one they
#: reach from a call-to-action on all of them, and the choice they made
#: elsewhere then had no visible control to undo it. The button is an icon, so
#: the current mode rides on the tooltip rather than on a word that changes
#: width at every click.
THEME_TOGGLE_JS = """\
const root=document.documentElement,tBtn=document.getElementById('themeBtn');
const tOrd=['auto','light','dark'];
let th=localStorage.getItem('docir-theme')||'auto';
const TH_ICON={auto:'◐',light:'☀',dark:'☾'};
function setTh(v){th=v;
  if(v==='auto')delete root.dataset.theme;else root.dataset.theme=v;
  tBtn.textContent=TH_ICON[v];tBtn.title='theme: '+v;
  localStorage.setItem('docir-theme',v);}
tBtn.onclick=()=>setTh(tOrd[(tOrd.indexOf(th)+1)%3]);
setTh(th);
"""
