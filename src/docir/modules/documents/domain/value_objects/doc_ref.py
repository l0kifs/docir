"""The :class:`DocRef` value object — one address a deep read accepts.

A batch read names several documents at once, and some of them by *section*:
`context` ranks a document on its best-matching heading, so the address an agent
already holds is a pair. The compact form is ``<id>`` or ``<id>#<heading>``.

The id grammar (``<prefix>-<suffix>``) never contains ``#``, so the first hash
unambiguously separates the two — the same argument :class:`RelatedRef` makes
about its colon. Splitting on the *first* one is what lets a heading keep its
own hashes (``adr-0001#Why #1 matters``).

Parsing is strict where :meth:`RelatedRef.parse` is lenient, because the two
sit on opposite sides of the write path. A malformed edge token is data being
read back; a malformed ref is a caller mistyping an address *now*, and the only
readings of ``adr-0001#`` are "the whole document" and "a heading I forgot to
type" — guessing the first returns a body nobody asked for and reports success.
"""

from __future__ import annotations

from dataclasses import dataclass

from docir.platform.errors import ValidationError

#: Separates the id from the heading in the compact form.
SECTION_MARKER = "#"


@dataclass(frozen=True, slots=True)
class DocRef:
    """A document id, optionally narrowed to one of its sections."""

    doc_id: str
    section: str | None = None

    @classmethod
    def parse(cls, token: str) -> DocRef:
        """Parse a ``<id>`` / ``<id>#<heading>`` address, refusing an empty half."""
        raw = token.strip()
        if not raw:
            raise ValidationError("empty document reference")
        doc_id, marker, section = raw.partition(SECTION_MARKER)
        doc_id, section = doc_id.strip(), section.strip()
        if not doc_id:
            raise ValidationError(f"{token!r} names a section but no document")
        if marker and not section:
            raise ValidationError(
                f"{token!r} ends in {SECTION_MARKER!r} but names no heading; "
                f"drop it to read the whole document"
            )
        return cls(doc_id=doc_id, section=section or None)

    def to_token(self) -> str:
        """The compact form, as the caller would have to type it again."""
        if self.section is None:
            return self.doc_id
        return f"{self.doc_id}{SECTION_MARKER}{self.section}"
