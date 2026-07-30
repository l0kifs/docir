"""Data-transfer objects crossing the tags module boundary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TagView:
    """A serialization-friendly projection of a :class:`Tag`.

    ``usage`` is a projection, not part of the :class:`Tag` entity: a tag is a
    key and a description, and how many documents happen to carry it is a fact
    about the corpus rather than about the tag.
    """

    key: str
    description: str
    #: Indexed documents carrying this tag, archived included — the same set
    #: ``tag rm`` refuses to remove over. ``0`` means the tag is dead and can be
    #: removed without ``--force``.
    usage: int = 0
