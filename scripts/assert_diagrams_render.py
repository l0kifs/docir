#!/usr/bin/env python3
"""Assert a published site's mermaid diagrams actually draw (pages.yml).

The step this replaces checked that ``mermaid.min.js`` exists in the output. That
is a weaker claim than it reads as, and the gap is exactly where a real defect
lived: docir's guidance named mermaid 10.9.3 on the grounds that 11 is ESM-only,
while the workflow published with 11.16.1 (issue-28e5dc0191cd). Had the reverse
been true — a bundle that no longer sets ``window.mermaid`` — every page would
have shipped its diagram as source, the runtime file would still have been
present, and the check would still have passed.

So this loads the pages in a real browser and asserts an ``<svg>`` with real
content exists inside each diagram node. "The runtime loaded" and "the diagram
drew" are different claims, and only the second is worth publishing on.

Served over HTTP rather than opened from ``file://``: Chromium blocks the
protocol under automation, and a site that works over HTTP is what Pages serves.
(docir's own runtime is loaded with a *relative classic script* precisely so the
site also works from disk — adr-9c7c1ab8acef — but that is not what this proves.)

Usage: ``python scripts/assert_diagrams_render.py <site-dir>``
Exits 0 when every diagram drew, 1 otherwise. A site with no diagrams at all is
also a failure: this repository's architecture note carries one, so "none found"
means the fence stopped being recognised.
"""

from __future__ import annotations

import functools
import http.server
import re
import socket
import socketserver
import sys
import threading
from pathlib import Path

#: The class docir puts on a rendered mermaid fence.
DIAGRAM_SELECTOR = ".docir-mermaid"

#: Which pages actually carry a diagram. It matches the class *attribute*, not
#: the bare name: docir inlines the mermaid CSS and its init script into every
#: page, so a plain substring search matched 185 of 372 pages on this store while
#: exactly one holds a `<div class="docir-mermaid">`. Every extra page then
#: waited out the selector timeout, turning a check into a hang — the same shape
#: as `test_agent_guide_matches_cli.py`'s regex, which reported 28 valid
#: invocations while extracting none of the line it existed to catch.
_DIAGRAM_ELEMENT = re.compile(r'class="[^"]*\bdocir-mermaid\b')

#: An SVG mermaid produced has a substantial element tree. A handful of nodes
#: means an error placeholder, which mermaid renders in place of a diagram.
MIN_SVG_ELEMENTS = 10


def _serve(directory: Path) -> tuple[str, socketserver.TCPServer, threading.Thread]:
    """Serve ``directory`` on a free port; return the base URL and the server."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = socketserver.TCPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{port}", server, thread


def _pages_with_diagrams(site: Path) -> list[Path]:
    """Every page carrying a diagram node, found by reading the HTML."""
    return sorted(
        path
        for path in site.rglob("*.html")
        if _DIAGRAM_ELEMENT.search(path.read_text(encoding="utf-8", errors="ignore"))
    )


def _check(site: Path) -> int:
    pages = _pages_with_diagrams(site)
    if not pages:
        print(f"::error::no page in {site} carries a {DIAGRAM_SELECTOR} node")
        return 1
    # Named, not counted: a count cannot tell "every diagram drew" from "the
    # scan found the wrong pages", which is how this script's first version
    # matched 185 pages of inlined CSS.
    total = len(list(site.rglob("*.html")))
    print(f"{len(pages)} of {total} page(s) carry a diagram: {[p.name for p in pages]}")

    from playwright.sync_api import sync_playwright

    base, server, _thread = _serve(site)
    failures = 0
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            for path in pages:
                relative = path.relative_to(site).as_posix()
                page.goto(f"{base}/{relative}", wait_until="load")
                # The runtime renders after load and re-renders on theme change,
                # so wait for the node to hold an svg rather than sampling once.
                try:
                    page.wait_for_selector(f"{DIAGRAM_SELECTOR} svg", timeout=15_000)
                except Exception:
                    print(f"::error::{relative}: no diagram drew — the runtime did not render")
                    failures += 1
                    continue
                counts = page.eval_on_selector_all(
                    DIAGRAM_SELECTOR,
                    "nodes => nodes.map(n => { const s = n.querySelector('svg');"
                    " return s ? s.querySelectorAll('*').length : 0; })",
                )
                thin = [count for count in counts if count < MIN_SVG_ELEMENTS]
                if thin:
                    print(
                        f"::error::{relative}: {len(thin)} diagram(s) rendered "
                        f"{thin} elements — mermaid draws an error placeholder that small"
                    )
                    failures += 1
                    continue
                print(f"{relative}: {len(counts)} diagram(s) drew, {counts} elements")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    return 1 if failures else 0


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} <site-dir>", file=sys.stderr)
        return 2
    site = Path(sys.argv[1])
    if not site.is_dir():
        print(f"::error::{site} is not a directory")
        return 1
    return _check(site)


if __name__ == "__main__":
    raise SystemExit(main())
