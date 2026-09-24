"""The on-disk format of a document: markdown body, YAML frontmatter block.

Split out of :mod:`markdown_store`, which changed for two unrelated reasons —
where a file goes, and what is written in it. This half is the one that is an
*interface*: the same ``.docir/`` is read by whatever docir each teammate
installed and by every repository declaring it a peer, so a change here is a
change against builds already in the wild, where the storage layout is local.

Round-tripping is load-bearing in both directions. A default-kind edge stays a
bare string so documents authored before typed edges keep their exact form, and
``target`` is accepted as a synonym for ``to`` on read because the JSON read
paths emit the first while the file format writes the second.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime

import frontmatter
import yaml

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.value_objects.relations import (
    DEFAULT_RELATION_KIND,
    RelatedRef,
)
from docir.platform.errors import ValidationError


def render(document: Document) -> str:
    """Serialize a document to markdown with a YAML frontmatter block.

    Optional keys are written only when set, so a document with no owner, no
    review state and no governed code keeps a minimal block. Each such key
    notes below why it lives in the *file* rather than the index: the index
    is gitignored, so anything a teammate has to read in a diff belongs here.
    """
    metadata: dict[str, object] = {
        "id": document.id,
        "title": document.title,
        "description": document.description,
        "type": document.type,
        "status": document.status,
        "tags": list(document.tags),
        "related": _render_related(document.related),
        "created": document.created.isoformat(),
        "updated": document.updated.isoformat(),
    }
    if document.archived:
        metadata["archived"] = True
    # Stewardship metadata is written only when set, so untyped/unowned docs
    # keep a minimal, clean frontmatter block.
    if document.owner:
        metadata["owner"] = document.owner
    if document.verified is not None:
        metadata["verified"] = document.verified.isoformat()
    # The other half of the review clock, and in the file for the same
    # reason `verified` is: it is what the cadence runs from once a
    # verification has been withdrawn, so a teammate who clones the repo has
    # to be able to read why a document is not due yet.
    if document.revoked is not None:
        metadata["revoked"] = document.revoked.isoformat()
    # In the file for the reason every other piece of review state is: the
    # index is gitignored, so a digest that lived only there would make
    # "this is not what was verified" a fact only the machine that stamped
    # it could know.
    if document.verified_content:
        metadata["verified_content"] = document.verified_content
    # Same rule as the stewardship keys: absent rather than an empty list,
    # so a document that governs no code carries no `code:` line at all.
    if document.code:
        metadata["code"] = list(document.code)
    # In the file rather than the index, unlike the schema baseline and the
    # build stamp: this is the document's review state, so a teammate who
    # clones the repo has to see it. The index is gitignored, and a digest
    # that lived only there would make "the code moved since somebody read
    # this" a fact only the machine that stamped it could know.
    if document.verified_code:
        metadata["verified_code"] = dict(sorted(document.verified_code.items()))
    # The authorship half of the same evidence, in the file for the same
    # reason and written under the same rule: absent rather than empty, so a
    # document governing no code carries no key, and a store written by a
    # build without the baseline round-trips byte-for-byte.
    if document.code_baseline:
        metadata["code_baseline"] = dict(sorted(document.code_baseline.items()))
    # Same rule again, and here it is what makes the exemption reviewable:
    # `isolated:` is a judgement about the corpus, so it belongs in the file
    # a teammate reads in a diff, not in the gitignored index.
    if document.isolated:
        metadata["isolated"] = document.isolated
    post = frontmatter.Post(content=document.body)
    post.metadata.update(metadata)
    return frontmatter.dumps(post) + "\n"


def parse(text: str, path: str) -> Document:
    """Parse one file's text into a document, or raise naming the file.

    Takes the text rather than a path: reading a file is the store's job, and
    mapping YAML onto the aggregate is this module's. ``path`` is carried only
    so a refusal can name the file the reader has to go and fix.
    """
    try:
        post = frontmatter.loads(text)
    except yaml.YAMLError as exc:
        raise ValidationError(f"malformed frontmatter in {path}: {exc}") from exc
    return _to_document(post.metadata, post.content, path)


def repeated_entries(text: str) -> dict[str, tuple[str, ...]]:
    """The entries each list field names more than once, in first-seen order.

    Read from the text because nothing else still holds them: the
    :class:`Document` built from the same file keeps each entry once. An edge
    is compared by what it says, so a bare `adr-1` and `{to: adr-1}` are one
    edge named twice, while two kinds to one target are two edges. Call it only
    on text :func:`parse` accepts.
    """
    metadata = frontmatter.loads(text).metadata
    lists = {
        "tags": _as_str_tuple(metadata.get("tags")),
        "code": _as_str_tuple(metadata.get("code")),
        "related": tuple(ref.to_token() for ref in _as_related_tuple(metadata.get("related"))),
    }
    return {field: repeats for field, values in lists.items() if (repeats := _named_twice(values))}


def _named_twice(values: tuple[str, ...]) -> tuple[str, ...]:
    counts = Counter(values)
    return tuple(value for value, count in counts.items() if count > 1)


def _to_document(metadata: dict[str, object], body: str, path: str) -> Document:
    try:
        verified_raw = metadata.get("verified")
        revoked_raw = metadata.get("revoked")
        return Document(
            id=str(metadata["id"]),
            title=str(metadata["title"]),
            description=str(metadata.get("description", "")),
            type=str(metadata["type"]),
            status=str(metadata["status"]),
            created=_as_date(metadata["created"]),
            updated=_as_date(metadata["updated"]),
            tags=_as_str_tuple(metadata.get("tags")),
            related=_as_related_tuple(metadata.get("related")),
            archived=bool(metadata.get("archived", False)),
            body=body,
            path=path,
            owner=str(metadata.get("owner", "")),
            verified=None if verified_raw is None else _as_date(verified_raw),
            revoked=None if revoked_raw is None else _as_date(revoked_raw),
            verified_content=str(metadata.get("verified_content", "")),
            code=_as_str_tuple(metadata.get("code")),
            verified_code=_as_str_map(metadata.get("verified_code")),
            code_baseline=_as_str_map(metadata.get("code_baseline")),
            isolated=str(metadata.get("isolated", "")),
        )
    except (KeyError, ValueError) as exc:
        # KeyError: a required field is absent. ValueError: a field is present
        # but unparseable (e.g. a ``created``/``updated`` that is not an ISO date).
        raise ValidationError(f"malformed frontmatter in {path}: {exc}") from exc


def _as_date(value: object) -> date:
    """Coerce a frontmatter date value (date or ISO string) to ``date``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _as_str_tuple(value: object) -> tuple[str, ...]:
    """Coerce a frontmatter list value into a tuple of strings."""
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    return ()


def _as_str_map(value: object) -> dict[str, str]:
    """Coerce a frontmatter mapping value into a ``str -> str`` dict.

    Anything that is not a mapping reads as absent rather than raising. A
    hand-edited ``verified_code:`` is bookkeeping, not content: refusing to
    parse the document over it would make a mistyped digest hide the title, the
    body and every edge the file carries.
    """
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    return {}


def _render_related(related: tuple[RelatedRef, ...]) -> list[object]:
    """Serialize edges: a bare id for the default kind, a mapping otherwise.

    Default-kind edges stay bare strings so documents authored before typed
    edges (``related: [adr-0001]``) round-trip byte-for-byte.
    """
    rendered: list[object] = []
    for ref in related:
        if ref.kind == DEFAULT_RELATION_KIND:
            rendered.append(ref.target)
        else:
            rendered.append({"to": ref.target, "kind": ref.kind})
    return rendered


def _as_related_tuple(value: object) -> tuple[RelatedRef, ...]:
    """Parse the ``related`` frontmatter (bare ids and/or ``{to, kind}`` maps).

    ``target`` is accepted as a synonym for ``to``: the JSON read paths emit
    ``{target, kind}`` while the file format writes ``{to, kind}``, so anyone —
    or any agent — who reads output and then hand-writes frontmatter reaches for
    the wrong key. ``to`` stays canonical on write, so files do not churn.
    """
    if not isinstance(value, list | tuple):
        return ()
    refs: list[RelatedRef] = []
    for item in value:
        if isinstance(item, dict):
            target = str(item.get("to") or item.get("target") or "").strip()
            if not target:
                raise ValueError(f"related entry {item!r} is missing a 'to' (or 'target') id")
            kind = str(item.get("kind", DEFAULT_RELATION_KIND)).strip() or DEFAULT_RELATION_KIND
            refs.append(RelatedRef(target=target, kind=kind))
        else:
            refs.append(RelatedRef(target=str(item).strip()))
    return tuple(refs)
