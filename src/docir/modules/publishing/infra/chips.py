"""The vocabulary that classifies a document, wherever it is shown.

One module because these are one vocabulary, not because every one of them has
two callers — four are used only by the document page, and the rest by the index
or the shell. Splitting them by consumer would let a status chip drift between
the list and the page it links to, which is the defect below arriving by a
different door.

**Type, status and tags look different**, and that came from reading a rendered
page rather than the markup. As identical grey chips, one page read
``architecture · active · architecture · persistence · retrieval`` —
"architecture" appearing twice meaning two different things, with nothing to say
which was which. Each now has its own treatment, and a ``title`` for the reader
who hovers rather than guesses.
"""

from __future__ import annotations

import html

from docir.modules.publishing.domain.site import SiteDocument

#: Semantic colour per status *name*. The site receives no schema, so statuses
#: are recognised the way the graph page recognises inactive ones — by the
#: bundled profiles' vocabularies. An unknown status renders as the neutral
#: chip rather than guessing a meaning; a wrong colour is worse than none.
_STATUS_CLASS = {
    "accepted": "st-good",
    "active": "st-good",
    "open": "st-good",
    "published": "st-good",
    "supported": "st-good",
    "superseded": "st-warn",
    "deprecated": "st-warn",
    "breached": "st-warn",
    "rejected": "st-bad",
    "resolved": "st-done",
    "complete": "st-done",
}

#: Type names that are mass nouns: "3 architecture documents", never
#: "3 architectures". The naive +s rule is right for the countable bundled
#: types (decisions, issues, runbooks) and wrong for these two, and a heading
#: reading "Architectures" is the kind of blemish that makes a generated site
#: look generated.
_UNCOUNTABLE_TYPES = frozenset({"architecture", "reference", "research", "documentation"})


def id_chip(document: SiteDocument) -> str:
    # The docir id is the one index a document has; it appears in mono
    # wherever chrome needs identity, and matches the copyable CLI command.
    return f'<span class="chip docid" title="document id">{html.escape(document.id)}</span>'


def type_chip(document: SiteDocument) -> str:
    return f'<span class="chip type" title="document type">{html.escape(document.type)}</span>'


def status_chip(document: SiteDocument) -> str:
    semantic = _STATUS_CLASS.get(document.status)
    cls = f"chip status {semantic}" if semantic else "chip status"
    return f'<span class="{cls}" title="status">{html.escape(document.status)}</span>'


def tag_chips(document: SiteDocument) -> str:
    # The `#` is the label. A word of prose per chip would be noise; the sigil
    # is read instantly and is what a tag looks like everywhere else.
    return "".join(
        f'<span class="chip tag" title="tag">#{html.escape(tag)}</span>' for tag in document.tags
    )


def state_chips(document: SiteDocument) -> str:
    chips = ""
    if document.stale:
        chips += '<span class="chip stale" title="past its review cadence">⚠ stale</span>'
    if document.archived:
        chips += '<span class="chip archived" title="archived">archived</span>'
    return chips


def type_label(type_name: str, *, plural: bool = False) -> str:
    """A type as a heading reads it: `release_note` -> `Release notes`.

    The schema's identifiers are snake_case singulars because they are keys;
    a nav group listing eighteen of them is prose. Pluralisation is the naive
    English rule minus the mass nouns above — harmless for a custom type,
    where a wrong plural is cosmetic and an unreadable key is not. Facet
    options deliberately keep the raw key: they have to match the
    `type:release_note` token the same filter box accepts.
    """
    words = type_name.replace("_", " ")
    label = words[:1].upper() + words[1:] if words else words
    if plural and not label.endswith("s") and type_name not in _UNCOUNTABLE_TYPES:
        label += "s"
    return label


def type_dot(type_name: str) -> str:
    """A colour swatch for a type — always beside the type's name.

    The name is the encoding; the colour is reinforcement. Types outside the
    token palette fall back to the muted grey rather than minting a hue the
    graph would not agree with.
    """
    return (
        f'<span class="dot" '
        f'style="background:var(--t-{html.escape(type_name)},var(--muted))"></span>'
    )


def verified_cell(document: SiteDocument) -> str:
    """What the trust panel says about the document's review claim.

    "never" is right for a document nobody vouched for and wrong for one whose
    verification was withdrawn — the page would deny a review the corpus
    records, and hide the date the cadence is now running from.
    """
    if document.verified:
        return document.verified
    if document.revoked:
        return f"withdrawn {document.revoked}"
    return "never"
