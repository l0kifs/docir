"""The one way a document is persisted: the row and the edges its body implies.

Every writer in this module goes through :func:`save_with_mentions` — the write
path, the rebuild, the repair. One function rather than two calls at each write
site, for the reason the embedding queue does the opposite and gets away with
it: a missed ``mark_dirty`` leaves a vector stale until the next write, while a
missed mention silently makes ``orphan`` report a document whose author *did*
link it — the exact false positive the mention graph exists to remove. A rebuild
or a repair that refreshed metadata and left the derived graph behind would make
the recovery commands the ones that create the problem.

The scan is derivation, not storage, so it happens here and not in the
repository: ``platform.persistence`` translates rows and entities and has no
business knowing what a body means (it may not import ``platform.naming``
either, which is tach saying the same thing).

``tags`` writes documents too and deliberately does not call this: a tag rename
rewrites frontmatter and never the body, so the mentions it would recompute are
the ones already stored.
"""

from __future__ import annotations

from docir.modules.documents.domain.entities.document import Document
from docir.platform.persistence.unit_of_work import UnitOfWork


def save_with_mentions(uow: UnitOfWork, document: Document, prefixes: frozenset[str]) -> None:
    """Persist a document and replace the mention edges its body implies.

    ``prefixes`` is the schema's id prefixes, resolved once per service because
    every save scans a body against it: the scan only recognises an id a type in
    this store could have minted, or ``sha-1beef`` in a sentence about hashing
    would be an edge.
    """
    uow.documents.save(document)
    uow.mentions.replace(document.id, document.mentioned_ids(prefixes))
