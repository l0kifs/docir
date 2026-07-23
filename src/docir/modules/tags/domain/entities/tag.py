"""The :class:`Tag` entity — a registered classifier.

Tags are not free-form strings: each is a registered entity with a unique key
and a description, versioned in git via ``docs/tags.yaml``. Referential
integrity (Tier 0) requires every key used by a document to exist here, which
eliminates synonym sprawl (``auth`` vs ``authentication`` vs ``Auth``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tag:
    """A registered tag: a unique key plus a human/agent-readable description."""

    key: str
    description: str
