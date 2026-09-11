"""The ``[[...]]`` prose link — its grammar, and the rule that resolves it.

A body cites another document two ways. ``related:`` frontmatter is the typed,
authored edge: validated on write, checked by ``dangling``, drawn on the graph.
``[[...]]`` written mid-sentence is the other one — navigational, untyped, and
for a long time resolved by nothing at all, so it published as literal brackets
and a retitle broke every inbound one in silence (adr-ae631a356639).

Two readers need the same answer and neither may import the other: ``documents``
reports the unresolved ones from ``docir check``, and ``publishing`` — a leaf
that takes documents as data — turns the resolved ones into links. So the rule
lives here, beside the tag-key and document-id grammars and for the same reason
(adr-289e788719a7): a link that resolves for the renderer and dangles for the
checker is worse than one that does neither.

**What a target may be.** Three forms, because all three are what people
actually write:

* the document id — ``[[adr-3f9a2b1c7d4e]]``, the only real address;
* the filename stem — ``[[adr-3f9a2b1c7d4e-how-auth-works]]``, what copying a
  path gives you, and *truncated*, which is why it cannot be derived from a
  title alone;
* the title slug — ``[[how-auth-works]]``, what writing one by hand gives you.

A raw title (``[[How auth works]]``) resolves too: it is slugified first, so the
form somebody types without knowing the convention lands on the same document.
A ``.md`` suffix and a leading directory are stripped, since both are what a
path looks like when pasted.

**What it resolves against.** Every document in the store, inactive and archived
included. A link to a resolved issue or a superseded decision is a *working*
link — following a decision to the one that replaced it is the point of having
the graph — and treating "not in the default query" as "broken" is the mistake
the issue's author made twice while counting by hand.

**Ambiguity is not resolution.** Two documents can share a title, so a title
slug can name both. Neither renderer nor checker guesses: the link stays text
and the check reports the candidates, because picking one silently is how a
reader ends up on the wrong document with no way to tell.

Pure: no I/O, no dependencies beyond :mod:`re`. See adr-289e788719a7.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from docir.platform.naming.slug import UNTRUNCATED, slugify

#: A ``[[...]]`` as written. Deliberately loose about what is inside: the target
#: is checked against the corpus, so a false positive cannot survive, and a
#: pattern that tried to encode the id/slug/stem grammar would stop matching the
#: day a store mints a fourth shape. Newlines and nested brackets are excluded
#: so an unclosed ``[[`` cannot swallow the rest of a paragraph.
WIKILINK_RE = re.compile(r"\[\[([^\[\]\n]+?)\]\]")

#: A fenced block's delimiter, matched the way :func:`scan_headings` matches it
#: — the two scanners have to agree about what is code.
_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")

#: An inline code span: a run of backticks, whatever is not that run, the run
#: again. Masked out before the link scan, so ```[[Target]]``` in a
#: sentence explaining the syntax is not read as a link to ``Target``.
_INLINE_CODE_RE = re.compile(r"(`+)(?:(?!\1).)*?\1")


@dataclass(frozen=True, slots=True)
class Wikilink:
    """One ``[[...]]``, split into the parts a reader wrote."""

    #: The document half — an id, a filename stem, a title slug or a title.
    target: str
    #: A heading inside it (``[[target#Why it matters]]``), or ``""``.
    section: str = ""
    #: Explicit link text (``[[target|the auth decision]]``), or ``""``.
    label: str = ""


@dataclass(frozen=True, slots=True)
class LinkTarget:
    """One document, as the resolver needs to see it."""

    doc_id: str
    title: str
    #: The filename stem (``adr-3f9a2b1c7d4e-how-auth-works``), or ``""`` when
    #: the document has no path yet. Carried rather than derived: ``update
    #: --set-title`` keeps the original filename, so a retitled document's stem
    #: is the *old* slug — and the inbound links written against it still have
    #: to resolve, which is the whole point.
    stem: str = ""


@dataclass(frozen=True, slots=True)
class LinkResolution:
    """What a target named: one document, none, or several."""

    #: The document, when exactly one matched.
    doc_id: str | None = None
    #: Every document the target matched, when more than one did.
    candidates: tuple[str, ...] = ()

    @property
    def is_ambiguous(self) -> bool:
        return self.doc_id is None and bool(self.candidates)


#: Nothing matched, and nothing was ambiguous about it.
UNRESOLVED = LinkResolution()


def parse_wikilink(inner: str) -> Wikilink | None:
    """Split what was between the brackets, or ``None`` if it names nothing.

    ``[[target#section|label]]`` is Obsidian's order and the one people arrive
    with. Both halves are optional; an empty target is not a link, so ``[[|x]]``
    and ``[[ ]]`` are left alone rather than reported as broken.
    """
    head, _, label = inner.partition("|")
    target, _, section = head.partition("#")
    target = target.strip()
    if not target:
        return None
    return Wikilink(target=target, section=section.strip(), label=label.strip())


def scan_wikilinks(body: str) -> tuple[Wikilink, ...]:
    """Every ``[[...]]`` in ``body``, in order, **skipping code**.

    Code is skipped here and nowhere else in docir's prose scanning, and the
    difference is deliberate. :func:`scan_document_ids` reads fences on purpose:
    an id inside ``docir get adr-…`` names that document as surely as a sentence
    would, and measured on this corpus 56 resolved mentions live *only* inside
    code spans, so filtering them would delete a working graph
    (adr-e86c5040d626).

    A ``[[...]]`` inside code is the opposite case. It was never a link — the
    renderer works from the markdown token stream, where a code span is opaque —
    so skipping it costs nothing and buys the discriminator the mention scanner
    could not have: this repository's only two ``[[...]]`` occurrences are both
    inside code spans, in the document explaining what a wikilink is. Read
    literally they would be the check's two findings, on the document doing its
    job — the failure mode that keeps `unresolved-mention` out of Tier 1.
    """
    links: list[Wikilink] = []
    in_fence = False
    for line in body.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in WIKILINK_RE.finditer(_INLINE_CODE_RE.sub(_blank, line)):
            if (link := parse_wikilink(match.group(1))) is not None:
                links.append(link)
    return tuple(links)


def _blank(match: re.Match[str]) -> str:
    """Replace a code span with spaces, keeping the line's length and offsets."""
    return " " * len(match.group(0))


def normalize_target(target: str) -> str:
    """The lookup key for a target, as written.

    A pasted path is still a target: the directory and the ``.md`` are noise
    around the part that identifies the document.
    """
    text = target.strip().replace("\\", "/").rsplit("/", 1)[-1].strip()
    if text.lower().endswith(".md"):
        text = text[:-3]
    return text.strip().lower()


class LinkIndex:
    """Resolves ``[[...]]`` targets against a corpus.

    Built once per command over every document, including the inactive and
    archived ones. Three lookups, tried in order of how exact they are: an id, a
    filename stem, then a title slug — the only one that can be ambiguous, since
    ids and stems carry an id and titles do not.
    """

    __slots__ = ("_by_id", "_by_slug", "_by_stem", "_titles")

    def __init__(self, targets: Iterable[LinkTarget] = ()) -> None:
        self._by_id: dict[str, str] = {}
        self._by_stem: dict[str, str] = {}
        self._by_slug: dict[str, list[str]] = {}
        self._titles: dict[str, str] = {}
        for target in targets:
            self._add(target)

    def _add(self, target: LinkTarget) -> None:
        self._by_id[target.doc_id.lower()] = target.doc_id
        self._titles[target.doc_id] = target.title
        if target.stem:
            self._by_stem[target.stem.lower()] = target.doc_id
        if not target.title:
            return
        # Both lengths: the file carries the truncated slug, a hand-written
        # link carries the whole title, and each is what somebody has in front
        # of them when they type the link.
        for slug in {slugify(target.title), slugify(target.title, max_length=UNTRUNCATED)}:
            bucket = self._by_slug.setdefault(slug, [])
            if target.doc_id not in bucket:
                bucket.append(target.doc_id)

    def resolve(self, target: str) -> LinkResolution:
        """Which document ``target`` names."""
        key = normalize_target(target)
        if not key:
            return UNRESOLVED
        if (doc_id := self._by_id.get(key)) is not None:
            return LinkResolution(doc_id=doc_id)
        if (doc_id := self._by_stem.get(key)) is not None:
            return LinkResolution(doc_id=doc_id)
        # Slugified, so a raw title reaches the same bucket its slug does.
        matches = self._by_slug.get(key) or self._by_slug.get(
            slugify(key, max_length=UNTRUNCATED), []
        )
        if len(matches) == 1:
            return LinkResolution(doc_id=matches[0])
        return LinkResolution(candidates=tuple(matches))

    def title(self, doc_id: str) -> str:
        """The document's title, for link text. Empty when it is not indexed."""
        return self._titles.get(doc_id, "")
