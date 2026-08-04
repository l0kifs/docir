"""The site's colour tokens — one place, imported by every page renderer.

Split out of ``rendering.py`` so the graph page can share the exact same
palette without a circular import (``rendering`` composes the site and so
imports ``graph``; ``graph`` must not import ``rendering`` back). A page that
declared its own near-identical tokens would drift the first time someone
tuned a colour in only one of them.
"""

from __future__ import annotations

CSS_TOKENS = """\
:root{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#e3e3e3;--accent:#0b5fff;
--chip:#f2f4f7;--warn:#8a5a00;--warn-bg:#fff5e0;--code:#f6f8fa;--panel:#fafbfc}
@media(prefers-color-scheme:dark){:root{--bg:#14161a;--fg:#e8e8e8;--muted:#9aa0aa;
--line:#2a2e35;--accent:#7aa7ff;--chip:#22262d;--warn:#ffcf70;--warn-bg:#3a2f14;
--code:#1c2027;--panel:#191c21}}
"""

#: An empty data: URI. Browsers request /favicon.ico on every page and log a
#: 404 when it is absent; this answers it without a network request, so the
#: page stays offline-complete.
FAVICON = '<link rel="icon" href="data:,">'
