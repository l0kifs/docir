"""The :class:`RelatedRef` value object — a typed outgoing link.

Each entry in a document's ``related`` list is a *typed* edge: a target id plus
a relation *kind* (``supersedes``, ``depends_on``, ``implements``,
``contradicts``, or the generic default ``relates_to``). Typed edges give agents
exact, cheap graph traversal and let the schema constrain which relations a type
may declare — embeddings become the fallback for "I don't know the right doc",
not the primary path.

The on-disk / CLI compact form is ``<id>`` (default kind) or ``<id>:<kind>``.
The id grammar (``<prefix>-<suffix>``) never contains ``:``, so the first colon
unambiguously separates the id from the kind.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The kind assigned to an edge written as a bare id (no explicit kind). Chosen
#: so a plain ``related: [adr-0001]`` keeps its exact on-disk form — untyped
#: documents authored before typed edges round-trip unchanged.
DEFAULT_RELATION_KIND = "relates_to"


@dataclass(frozen=True, slots=True)
class RelatedRef:
    """A typed outgoing link: the target id and the relation kind."""

    target: str
    kind: str = DEFAULT_RELATION_KIND

    @classmethod
    def parse(cls, token: str, *, default_kind: str = DEFAULT_RELATION_KIND) -> RelatedRef:
        """Parse a ``<id>`` or ``<id>:<kind>`` compact token into a ref."""
        raw = token.strip()
        target, sep, kind = raw.partition(":")
        target = target.strip()
        kind = kind.strip()
        return cls(target=target, kind=kind if sep and kind else default_kind)

    def to_token(self) -> str:
        """The compact ``<id>`` / ``<id>:<kind>`` form (bare when default kind)."""
        if self.kind == DEFAULT_RELATION_KIND:
            return self.target
        return f"{self.target}:{self.kind}"
