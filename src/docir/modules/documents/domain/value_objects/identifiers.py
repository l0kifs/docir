"""The :class:`DocId` value object.

A document id has the form ``<type-prefix>-<suffix>``, where the suffix is
a zero-padded sequential number (``adr-0007``), a random hex token
(``adr-3f9a2b1c7d4e``) or a time-ordered hex token (``adr-6ab51e1481ab``),
depending on the type's ``id_style``. Sequential ids are human-friendly but
only collision-free within a single shared index; random and chronological ids
trade readability for collision-resistance across independent clones and git
branches, and chronological ids also sort by creation time. Ids are always
allocated by the CLI, never chosen by hand.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from docir.platform.errors import ValidationError
from docir.platform.naming import DOC_ID_RE

# Suffix is 4+ lowercase hex chars — covers both decimal sequential numbers
# (digits are a subset of hex) and random hex tokens. The pattern itself lives
# in `platform.naming`, because the mention scanner has to recognise inside
# prose exactly what this mints (adr-289e788719a7): two copies would let a
# document be addressable by one reader and invisible to the other.
_ID_RE = DOC_ID_RE

# Bytes of entropy for random ids: 6 bytes = 48 bits = 12 hex chars, giving a
# negligible collision probability at this scale (thousands of documents).
_RANDOM_ENTROPY_BYTES = 6

#: Length of a random id's suffix, in hex characters.
RANDOM_SUFFIX_LENGTH = _RANDOM_ENTROPY_BYTES * 2

# A chronological suffix is the creation second in fixed-width lowercase hex,
# then random hex. The width is fixed because the sort order of the filenames
# is the whole point: for equal-width lowercase hex, lexicographic order is
# numeric order, so ids sort by time. Eight chars hold unix seconds up to 2106.
# The total matches RANDOM_SUFFIX_LENGTH, so `looks_random` covers both shapes.
_CHRONOLOGICAL_TIME_WIDTH = 8
_CHRONOLOGICAL_ENTROPY_BYTES = (RANDOM_SUFFIX_LENGTH - _CHRONOLOGICAL_TIME_WIDTH) // 2
_CHRONOLOGICAL_SECONDS_LIMIT = 16**_CHRONOLOGICAL_TIME_WIDTH


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

    @classmethod
    def build_chronological(cls, prefix: str, epoch_seconds: int) -> DocId:
        """Compose a collision-resistant :class:`DocId` that sorts by creation time.

        ``epoch_seconds`` is the creation instant in unix seconds, supplied by the
        caller so this stays free of any clock.
        """
        if not 0 <= epoch_seconds < _CHRONOLOGICAL_SECONDS_LIMIT:
            raise ValidationError(
                f"cannot mint a chronological id at {epoch_seconds} seconds: "
                f"its time part holds {_CHRONOLOGICAL_TIME_WIDTH} hex digits"
            )
        time_part = f"{epoch_seconds:0{_CHRONOLOGICAL_TIME_WIDTH}x}"
        return cls(f"{prefix}-{time_part}{secrets.token_hex(_CHRONOLOGICAL_ENTROPY_BYTES)}")

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
        """Whether this id has the shape of a hex token rather than a counter.

        Hex digits include the decimal digits, so roughly one random token in 281
        is all-digits — and a chronological one whenever its timestamp and tail
        happen to be — and parses as a perfectly good :attr:`number`. Length
        disambiguates: a counter would have to reach a hundred billion documents
        to produce a suffix this long.
        """
        return len(self.suffix) >= RANDOM_SUFFIX_LENGTH

    @property
    def leading_second(self) -> int | None:
        """The creation second a chronological suffix leads with, or ``None``.

        Read from any hex token, since the shape cannot tell a chronological one
        from a random one; for a random token the value is meaningless but still
        reproduces the token's current sort position, which is what a re-issue
        built on it needs.
        """
        if not self.looks_random:
            return None
        return int(self.suffix[:_CHRONOLOGICAL_TIME_WIDTH], 16)

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
