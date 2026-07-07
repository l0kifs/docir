"""The :class:`Relation` entity — a directed edge in the relation graph.

Each entry in a document's ``related`` list becomes one directed edge
``source -> target``. The set of edges forms the relation graph used for
one-hop context traversal and the Tier 1 graph checks (cycles, orphans,
layering violations).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Relation:
    """A directed ``source -> target`` link between two documents."""

    source: str
    target: str
