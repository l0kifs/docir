"""Data-transfer objects crossing the tags module boundary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TagView:
    """A serialization-friendly projection of a :class:`Tag`."""

    key: str
    description: str
