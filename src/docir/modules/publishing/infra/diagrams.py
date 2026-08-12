"""Mermaid fences in a body, published as diagrams.

A ``mermaid`` fence is the one code block an author does not mean as code —
they mean the picture it describes, which is how GitHub and every markdown
viewer the reader already uses render it. Published as a highlighted code
block, the sequence diagram in an architecture note is a wall of arrows the
reader has to compile in their head.

**The runtime is a build input, not a bundled asset** — the same call
``--logo`` makes (``infra/branding.py``). Mermaid's browser bundle is a few
megabytes of JavaScript: vendoring it would put it in every wheel, in every
CI image and in the supply chain of every install, to serve the fraction of
corpora that draw diagrams. So ``docir build --mermaid path/to/mermaid.min.js``
supplies it, docir writes it beside the pages, and a page that has a diagram
loads it from there.

Two properties are preserved on purpose:

* **The site stays offline-complete.** The runtime is written into the output
  directory and referenced relatively, never fetched from a CDN — a published
  site still opens from ``file://`` with no network, which is the guarantee
  the whole module is built around.
* **A missing runtime degrades to the source.** Without ``--mermaid`` the
  diagram element simply holds its own mermaid source as preformatted text,
  framed and copyable exactly like a code block. Nothing is hidden behind a
  script that did not load, and no page is worse than it is today.

The fallback is also why the source lives in the element's text rather than in
a ``data-`` attribute: the unrendered state *is* the source, so there is one
copy of it, and the bootstrap captures it in JavaScript before the first draw
in order to redraw on a theme change.
"""

from __future__ import annotations

import html
from pathlib import Path

from docir.platform.errors import ValidationError

#: The fence language that means "draw this".
LANGUAGE = "mermaid"

#: The class the bootstrap looks for, and the marker ``rendering`` tests a
#: rendered body against to decide whether the page needs the runtime. One
#: constant rather than a literal in three files: the emitter, the detector
#: and the script would otherwise drift the first time one was renamed.
DIAGRAM_CLASS = "docir-mermaid"

#: What the runtime is written as, and what the script tag references.
RUNTIME_FILE = "mermaid.min.js"

#: Cap on the supplied runtime. Mermaid's own minified bundle is ~3 MB; the
#: limit exists to catch a path that points at something else entirely (a
#: source tree, an archive) before it is copied into the site, and the error
#: names the file it expected.
MAX_RUNTIME_BYTES = 8 * 1024 * 1024

DIAGRAM_CSS = """\
/* ---- mermaid diagrams: the code block's frame, a picture inside ----
   Unrendered (no runtime supplied, or one that failed to load) the element
   still holds its source, so it is styled as preformatted text until the
   bootstrap marks it processed. */
figure.diagram{border:1px solid var(--line);border-radius:10px;overflow:hidden;
margin:1.2rem 0;background:var(--code)}
figure.diagram figcaption{display:flex;align-items:center;justify-content:space-between;
padding:.4rem .9rem;font-size:.76rem;color:var(--muted);
border-bottom:1px solid var(--line-soft);background:var(--chip)}
figure.diagram figcaption button{border:0;background:none;cursor:pointer;font:inherit;
font-size:.76rem;color:var(--muted);padding:0}
figure.diagram figcaption button:hover{color:var(--accent)}
.docir-mermaid{margin:0;padding:.9rem 1rem;overflow-x:auto;font-size:.84rem;line-height:1.6;
white-space:pre;font-family:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace}
.docir-mermaid[data-processed]{white-space:normal;text-align:center;font-family:inherit;
padding:1.1rem 1rem}
.docir-mermaid svg{max-width:100%;height:auto}
"""

#: Draws every diagram on the page, and redraws them when the theme changes.
#:
#: Mermaid picks its palette at ``initialize`` time and bakes it into the SVG,
#: so a diagram drawn in light mode stays light after the reader flips the
#: toggle — dark ink on a dark panel. Redrawing is the only fix, which is why
#: the sources are captured up front: by then the elements hold SVG.
#:
#: The resolved theme is compared against the last one drawn, so the
#: observer's own notification at load (the toggle sets ``data-theme`` on every
#: page) does not draw twice.
BOOTSTRAP_JS = """\
(function(){
var nodes=[].slice.call(document.querySelectorAll('.__CLS__'));
if(!nodes.length||!window.mermaid)return;
var src=nodes.map(function(n){return n.textContent;}),last=null;
function resolved(){var t=document.documentElement.dataset.theme;
if(t==='dark')return'dark';if(t==='light')return'default';
return window.matchMedia&&window.matchMedia('(prefers-color-scheme:dark)').matches
?'dark':'default';}
function draw(){var theme=resolved();if(theme===last)return;last=theme;
nodes.forEach(function(n,i){n.removeAttribute('data-processed');n.textContent=src[i];});
mermaid.initialize({startOnLoad:false,theme:theme,securityLevel:'strict'});
mermaid.run({nodes:nodes}).catch(function(){});}
draw();
new MutationObserver(draw).observe(document.documentElement,
{attributes:true,attributeFilter:['data-theme']});
if(window.matchMedia){var mq=window.matchMedia('(prefers-color-scheme:dark)');
mq.addEventListener?mq.addEventListener('change',draw):mq.addListener(draw);}
})();
""".replace("__CLS__", DIAGRAM_CLASS)


def render_diagram(source: str) -> str:
    """One mermaid fence as a figure: the frame of a code block, a picture inside.

    The copy button carries the source in ``data-copy`` rather than reading a
    sibling ``<pre>`` the way the code-block button does — after the runtime
    draws, the element holds an ``<svg>``, and a button that copied what it
    found would hand the reader a serialized diagram instead of the mermaid
    they wanted to reuse.
    """
    escaped = html.escape(source)
    return (
        '<figure class="diagram"><figcaption><span>Mermaid</span>'
        f'<button type="button" data-copy="{html.escape(source, quote=True)}">Copy</button>'
        f'</figcaption><div class="{DIAGRAM_CLASS}">{escaped}</div></figure>'
    )


def script_tags() -> str:
    """The runtime and its bootstrap, for a page that has at least one diagram.

    A classic script, not a module: a ``type="module"`` script is fetched under
    CORS rules that ``file://`` fails, so the site would draw over HTTP and
    silently show source when opened from disk — the one place it is most
    likely to be opened. This is also why the browser (UMD) bundle is what
    ``--mermaid`` expects.
    """
    return f'<script src="{RUNTIME_FILE}"></script>\n<script>{BOOTSTRAP_JS}</script>'


def resolve_runtime(runtime: Path | None) -> str | None:
    """Read the supplied mermaid bundle, or ``None`` to publish source-only.

    Read (and so validated) *before* the build removes anything, for the reason
    the logo is: a mistyped path should fail the build, not empty the output
    directory and then fail it.
    """
    if runtime is None:
        return None
    path = Path(runtime)
    if path.suffix.lower() != ".js":
        raise ValidationError(
            f"--mermaid expects a JavaScript bundle, got '{path.name}'; "
            "point it at mermaid's browser build (mermaid.min.js)"
        )
    if not path.is_file():
        raise ValidationError(f"mermaid runtime not found: {path}")
    data = path.read_bytes()
    if not data:
        raise ValidationError(f"mermaid runtime is empty: {path}")
    if len(data) > MAX_RUNTIME_BYTES:
        raise ValidationError(
            f"mermaid runtime is {len(data) // (1024 * 1024)} MB; the limit is "
            f"{MAX_RUNTIME_BYTES // (1024 * 1024)} MB — point --mermaid at the "
            "minified browser bundle, not a source tree"
        )
    return data.decode("utf-8", errors="replace")
