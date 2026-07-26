"""The :class:`DocId` value object.

A document id has the form ``<type-prefix>-<suffix>``, where the suffix is
either a zero-padded sequential number (``adr-0007``) or a random hex token
(``adr-3f9a2b1c7d4e``), depending on the type's ``id_style``. Sequential ids
are human-friendly but only collision-free within a single shared index; random
ids trade readability for collision-resistance across independent clones and
git branches. Ids are always allocated by the CLI, never chosen by hand.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass

from docir.platform.errors import ValidationError

# Suffix is 4+ lowercase hex chars — covers both decimal sequential numbers
# (digits are a subset of hex) and random hex tokens.
_ID_RE = re.compile(r"^(?P<prefix>[a-z][a-z0-9]*)-(?P<suffix>[0-9a-f]{4,})$")

# Bytes of entropy for random ids: 6 bytes = 48 bits = 12 hex chars, giving a
# negligible collision probability at this scale (thousands of documents).
_RANDOM_ENTROPY_BYTES = 6

#: Length of a random id's suffix, in hex characters.
RANDOM_SUFFIX_LENGTH = _RANDOM_ENTROPY_BYTES * 2


@dataclass(frozen=True, slots=True)
class DocId:
    """An immutable, validated document identifier."""

    value: str

    def __post_init__(self) -> None:
        if not _ID_RE.match(self.value):
            raise ValidationError(
                f"malformed document id {self.value!r}: expected '<prefix>-<suffix>'"
            )

    @classmethod
    def build(cls, prefix: str, number: int) -> DocId:
        """Compose a sequential :class:`DocId` from a prefix and an integer."""
        return cls(f"{prefix}-{number:04d}")

    @classmethod
    def build_random(cls, prefix: str) -> DocId:
        """Compose a collision-resistant :class:`DocId` with a random suffix."""
        return cls(f"{prefix}-{secrets.token_hex(_RANDOM_ENTROPY_BYTES)}")

    @property
    def prefix(self) -> str:
        """The type prefix portion of the id (e.g. ``adr``)."""
        match = _ID_RE.match(self.value)
        assert match is not None  # guaranteed by __post_init__
        return match.group("prefix")

    @property
    def suffix(self) -> str:
        """The suffix portion of the id (the sequential number or hex token)."""
        match = _ID_RE.match(self.value)
        assert match is not None  # guaranteed by __post_init__
        return match.group("suffix")

    @property
    def looks_random(self) -> bool:
        """Whether this id has the shape of a random token rather than a counter.

        Hex digits include the decimal digits, so roughly one random token in 281
        is all-digits and parses as a perfectly good :attr:`number`. Length
        disambiguates: a counter would have to reach a hundred billion documents
        to produce a suffix this long.
        """
        return len(self.suffix) >= RANDOM_SUFFIX_LENGTH

    @property
    def number(self) -> int:
        """The integer portion of a *sequential* id (e.g. ``7`` for ``adr-0007``).

        Raises :class:`ValidationError` for random (non-numeric) ids.
        """
        suffix = self.suffix
        if not suffix.isdigit():
            raise ValidationError(f"id {self.value!r} has no numeric component")
        return int(suffix)

    def __str__(self) -> str:
        return self.value
