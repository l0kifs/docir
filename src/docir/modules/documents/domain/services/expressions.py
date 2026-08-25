"""A user's question about their own corpus, as an expression (issue-9b2d2ab09060).

``docir query`` ships a fixed set of filters, and every question outside it was
a feature request. This is the grammar that stops that: a JMESPath expression
over a **projection** of one document — its own fields plus its edges resolved
in both directions — kept as a filter, so a truthy result keeps the document.

Two lines are load-bearing and neither is about JMESPath.

**docir ships no rules, only the ability to state one** (adr-b2cfed9d5888 refused
a rule engine, and that refusal survives this). What that decision refused was
docir having opinions about your architecture, plus a DSL of its own and a
sandbox for user code. JMESPath evaluates data; it cannot call out, import, or
loop unboundedly, so "run the user's expression" is not "run the user's code".
The moment a *shipped default* expression appears here, this has crossed back.

**The projection is the contract, not the ORM.** What a user writes an
expression against cannot change silently, so the shape below is public surface
and is spelled out in ``CONTRACT.md``. Adding a key is additive; renaming or
removing one breaks expressions written months ago against a corpus that still
parses.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import jmespath
from jmespath.exceptions import JMESPathError

from docir.modules.documents.domain.entities.document import Document
from docir.platform.errors import ValidationError

#: One edge, in whichever direction it was found. ``to`` is always the *other*
#: document, so an expression reads the same either way and only the list it
#: came from says which way the edge points. ``type``/``status`` are ``None``
#: when the corpus no longer carries the target — absent, not guessed.
EdgeView = dict[str, str | None]


def project(
    document: Document,
    *,
    stale: bool,
    outgoing: Sequence[EdgeView] = (),
    incoming: Sequence[EdgeView] = (),
) -> dict[str, Any]:
    """One document as the data an expression sees.

    Edges arrive **resolved** — each carries the other document's ``type`` and
    ``status``, not just its id. Unresolved ids would make the questions this
    feature exists for unanswerable: "an issue pointing at a decision that has
    since been superseded" is a question about the *target's* status, and a
    grammar that cannot ask it would ship without its motivating case.

    A target the corpus no longer carries keeps its id and reports ``type`` and
    ``status`` as ``null`` — absent, not guessed. That edge is a `dangling`
    finding and `docir check` is where it is reported; an expression should be
    able to see it, not be lied to about it.
    """
    return {
        "id": document.id,
        "type": document.type,
        "status": document.status,
        "title": document.title,
        "description": document.description,
        "tags": list(document.tags),
        "owner": document.owner or None,
        "verified": None if document.verified is None else document.verified.isoformat(),
        "created": document.created.isoformat(),
        "updated": document.updated.isoformat(),
        "archived": document.archived,
        "stale": stale,
        "code": list(document.code),
        "related": list(outgoing),
        "related_by": list(incoming),
    }


#: Every key :func:`project` puts on a document. Declared rather than derived
#: from a sample projection — that would be circular — and pinned by a test that
#: asserts ``project()`` returns exactly this set, so the two cannot drift.
PROJECTION_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "type",
        "status",
        "title",
        "description",
        "tags",
        "owner",
        "verified",
        "created",
        "updated",
        "archived",
        "stale",
        "code",
        "related",
        "related_by",
    }
)

#: Every key an edge carries inside ``related`` / ``related_by``.
EDGE_FIELDS: frozenset[str] = frozenset({"to", "kind", "type", "status"})


def _referenced_fields(node: object) -> set[str]:
    """Every identifier an expression reads, from the parsed AST.

    JMESPath emits a ``field`` node for each identifier access, and every
    identifier a caller can write refers to something in the projection — so
    walking these gives a complete list of what the expression expects to exist.
    """
    found: set[str] = set()
    if isinstance(node, dict):
        if node.get("type") == "field" and isinstance(node.get("value"), str):
            found.add(node["value"])
        for child in node.get("children") or ():
            found |= _referenced_fields(child)
    return found


def compile_expression(expression: str) -> jmespath.parser.ParsedResult:
    """Parse an expression, reporting a bad one where the caller typed it.

    Compiled once per query rather than per document: a syntax error is a
    property of the expression, and finding out on the first *matching*
    document would make the error depend on the corpus.

    Also refuses a name the projection does not carry, which is the more
    dangerous fault: an unknown identifier evaluates to ``null`` rather than
    raising, so a typo returns an empty result that cannot be told from a corpus
    with nothing wrong.
    """
    text = expression.strip()
    if not text:
        raise ValidationError("--expr needs an expression")
    try:
        compiled = jmespath.compile(text)
    except JMESPathError as exc:
        raise ValidationError(f"--expr is not a valid JMESPath expression: {exc}") from exc

    # A name the projection does not carry evaluates to null, so `stauts ==
    # 'open'` matches nothing and reads as a corpus with nothing wrong. Silent
    # is the one outcome a filter must not have: it cannot be told from a clean
    # answer, and a *declared* check with that typo would run forever finding
    # nothing (adr-9b36dc92fc07).
    unknown = sorted(_referenced_fields(compiled.parsed) - PROJECTION_FIELDS - EDGE_FIELDS)
    if unknown:
        known = ", ".join(sorted(PROJECTION_FIELDS))
        raise ValidationError(
            f"expression names {', '.join(repr(name) for name in unknown)}, which no document "
            f"carries; available: {known} (edges carry {', '.join(sorted(EDGE_FIELDS))})"
        )
    return compiled


def matches(compiled: jmespath.parser.ParsedResult, projection: Mapping[str, Any]) -> bool:
    """Whether a document satisfies the expression.

    Truthiness is JMESPath's own: ``null``, ``false``, ``0``, an empty string,
    list or object are all misses. That makes ``related_by[?kind=='supersedes']``
    read as a filter without a comparison bolted onto it, which is how the
    grammar's own users write it.

    An expression that raises on one document is a failed *query*, not a skipped
    row: silently dropping the document would answer the question wrongly and
    look like a small result.
    """
    try:
        return bool(compiled.search(dict(projection)))
    except JMESPathError as exc:
        raise ValidationError(f"--expr failed on {projection.get('id')!r}: {exc}") from exc
