"""The :class:`Relation` entity — a directed, typed edge in the relation graph.

Each entry in a document's ``related`` list becomes one directed edge
``source -> target`` carrying a *kind* (``supersedes``, ``depends_on``,
``implements``, ``contradicts``, or the generic default ``relates_to``). The set
of edges forms the relation graph used for one-hop context traversal and the
Tier 1 graph checks (cycles, orphans, layering violations).
"""

from __future__ import annotations

from dataclasses import dataclass

from docir.modules.documents.domain.value_objects.relations import DEFAULT_RELATION_KIND


@dataclass(frozen=True, slots=True)
class Relation:
    """A directed, typed ``source -> target`` link between two documents."""

    source: str
    target: str
    kind: str = DEFAULT_RELATION_KIND
