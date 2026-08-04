"""Public surface of the publishing module.

Renders a docir corpus into a self-contained static site — the human-browsable
half of a store that otherwise only an agent and a terminal can read. A decision
that only an agent can read is a hard sell to the people who have to approve it.

This module owns no index or database state and reads no repositories. It takes
the documents as **data** — the same JSON shape ``docir get`` returns — so it
stays a dependency leaf like ``agents``: the site is a projection of docir's
public contract, not a second reader of the document aggregate.
"""

from __future__ import annotations

from docir.modules.publishing.application.service import (
    MARKER_FILE,
    PublishRequest,
    PublishResult,
    SiteBuilder,
)
from docir.modules.publishing.domain.site import (
    Edge,
    Site,
    SiteDocument,
    build_site,
    graph_payload,
)


def build_site_builder() -> SiteBuilder:
    """Wire the site builder for one process."""
    return SiteBuilder()


__all__ = [
    "MARKER_FILE",
    "Edge",
    "PublishRequest",
    "PublishResult",
    "Site",
    "SiteBuilder",
    "SiteDocument",
    "build_site",
    "build_site_builder",
    "graph_payload",
]
