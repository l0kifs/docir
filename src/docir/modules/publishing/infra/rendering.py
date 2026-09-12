"""The published site, assembled: one page per document, the index, the graph.

Self-contained and offline by design — see :mod:`assets` for why every byte is
inlined. This module is the assembly step and nothing else: a document's HTML
comes from :mod:`document_page`, the index from :mod:`index_page`, the graph
from :mod:`graph`, and each is poured into the shell in :mod:`page_shell`.

Several decisions in this package came from opening the site in a browser rather
than from reading the markup, and each is easy to undo by accident. They are
recorded in the module whose code they govern, so that an edit meets the
measurement: the grid index in :mod:`index_page`, the relation placement in
:mod:`document_page`, the chip vocabulary in :mod:`chips`, the dropped leading
title in :mod:`markdown`, and the scoped class names in :mod:`assets`.
"""

from __future__ import annotations

import json

from docir.modules.publishing.domain.site import (
    Site,
    SiteDocument,
    link_index,
)
from docir.modules.publishing.infra import diagrams
from docir.modules.publishing.infra.branding import DOCIR_BRANDING, Branding
from docir.modules.publishing.infra.document_page import render_document
from docir.modules.publishing.infra.graph import render_graph_page
from docir.modules.publishing.infra.index_page import render_index
from docir.modules.publishing.infra.page_shell import page_name, source_name


def render_site(
    site: Site,
    *,
    title: str,
    version: str,
    branding: Branding = DOCIR_BRANDING,
    runtime: str | None = None,
) -> dict[str, str]:
    """Render the whole site as ``relative path -> file contents``.

    One page per document plus its markdown source, the index, and the graph —
    the corpus drawn as an interactive map. Returning content rather than
    writing it keeps this layer free of the filesystem, so a test can assert on
    the HTML without a temp directory and the writer has exactly one job.

    ``runtime`` is the mermaid bundle's source, when the publisher supplied one.
    It joins the returned files — and only if some page actually drew a diagram,
    which is knowable here and nowhere else: the bodies are rendered in
    :mod:`markdown`, but this is the layer that holds every finished page.
    A corpus with no mermaid in it publishes no megabyte of JavaScript.
    """
    by_id = {document.id: document for document in site.documents}
    # One resolver for the whole site: every page's prose links are looked up
    # against the same corpus, and building it per page would slugify every
    # title once per document.
    links = link_index(site)
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
        "index.html": render_index(site, title=title, version=version, branding=branding),
        "graph.html": render_graph_page(site, title=title, branding=branding),
    }
    for document in site.documents:
        pages[page_name(document.id)] = render_document(
            document,
            site=site,
            title=title,
            version=version,
            by_id=by_id,
            neighbors=neighbors[document.id],
            branding=branding,
            runtime=runtime is not None,
            links=links,
        )
        pages[source_name(document.id)] = document.body
    if runtime is not None and any(
        diagrams.loads_runtime(page) for name, page in pages.items() if name.endswith(".html")
    ):
        pages[diagrams.RUNTIME_FILE] = runtime
    return pages


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
