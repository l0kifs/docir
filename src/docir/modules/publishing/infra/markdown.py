"""Markdown to HTML: the token pipeline, and the two ways a body cites a document.

Rendered with ``markdown-it-py``, which docir already installs (Rich depends on
it). Bodies come from the store's own write path, not from the internet — but
they are still escaped where they are interpolated as text rather than rendered
as markdown, because a title is not markdown and a document titled ``<script>``
should read as a title.

A bare id and a ``[[...]]`` wikilink both become anchors here, and both resolve
through one index, so a retitle cannot break one and leave the other working.

**A body's leading ``# Title`` is dropped.** docir's own convention restates the
title as the body's first line, which published it twice — the second one
*larger*, because a body ``h1`` outranks the page heading.
"""

from __future__ import annotations

import html
import re
from collections.abc import Collection

from markdown_it import MarkdownIt
from markdown_it.token import Token

from docir.modules.publishing.infra import diagrams
from docir.modules.publishing.infra.highlight import highlight, language_label
from docir.modules.publishing.infra.page_shell import page_name
from docir.platform.naming.links import WIKILINK_RE, LinkIndex, Wikilink, parse_wikilink

_HEADING_CLOSE = re.compile(r"</h([1-6])>")

_ANCHOR_GLYPH = "¶"

#: Shape of a *candidate* docir id in prose. Deliberately loose — it only has to
#: bracket something worth looking up, and every match is then checked against
#: the ids the site actually publishes, so a false positive cannot survive. The
#: alternative, a real id grammar, would have to be kept in step with whatever
#: `id_style` mints (12 hex chars today, four digits in a sequential store) and
#: would silently stop linking the day a third style is added.
_DOC_ID_SHAPE = re.compile(r"\b[a-z][a-z0-9]*-[a-z0-9]{4,}\b")


def render_body(
    text: str,
    *,
    drop_title: str = "",
    known_ids: Collection[str] = (),
    links: LinkIndex | None = None,
) -> tuple[str, list[tuple[int, str, str]]]:
    """Render a body to HTML, id its headings, and report them.

    Ids come from the token stream rather than a regex over rendered HTML: the
    tokens already carry the level and the text, and rewriting generated markup
    to work out what it meant is how a renderer acquires a second parser.

    ``drop_title`` removes a leading level-1 heading that repeats the document
    title — docir's own convention restates it as the body's first line, which
    published the title twice with the second one larger.

    ``known_ids`` are the documents this site publishes; a bare docir id in the
    prose that names one of them becomes a link to its page. ``links`` resolves
    the other cross-reference syntax, ``[[...]]``, whose targets are not ids —
    without it those publish as the literal brackets they were written as.
    """
    parser = MarkdownIt("commonmark", {"linkify": False}).enable("table")
    # Both code token types, so an indented block is framed like a fenced one.
    parser.add_render_rule("fence", _render_fence)
    parser.add_render_rule("code_block", _render_fence)
    tokens = _drop_leading_title(parser.parse(text), drop_title)
    _linkify_refs(tokens, frozenset(known_ids), links or LinkIndex())

    headings: list[tuple[int, str, str]] = []
    seen: dict[str, int] = {}
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or index + 1 >= len(tokens):
            continue
        content = tokens[index + 1].content
        slug = _unique_slug(content, seen)
        token.attrSet("id", slug)
        headings.append((_level(token.tag), slug, content))

    rendered = parser.renderer.render(tokens, parser.options, {})
    return _inject_anchors(rendered, headings), headings


def _linkify_refs(tokens: list, known: frozenset[str], links: LinkIndex) -> None:
    """Turn both prose cross-reference syntaxes into links, in place.

    A body cites another document two ways, and both published as dead text.
    A bare docir id is the only identifier a document has — sequence labels
    inside titles are title text — so the one canonical way to cite a document
    was also the one that gave the reader nothing to follow. And ``[[...]]``,
    which people write because every other markdown tool resolves it, was
    rendered *worse* than untouched: the bracketed id matched the id scanner,
    so ``[[adr-3f9a2b1c7d4e]]`` published as a link wearing two stray brackets,
    and ``[[adr-3f9a2b1c7d4e-how-auth-works]]`` as a link with the slug hanging
    outside it (adr-ae631a356639). One pass handles both, which is what stops
    them overlapping.

    Operates on the token stream, not the rendered HTML, which is what keeps it
    from linking inside fenced code, and — via ``depth`` — from nesting an
    anchor inside a link whose text happens to be a reference. A ``code_inline``
    whose whole content is an id is wrapped rather than rewritten, so the
    existing ```id``` spelling keeps its mono styling and gains the link; a
    ``[[...]]`` inside code is left alone entirely, because a body showing the
    syntax is not using it. That is the same rule ``scan_wikilinks`` applies for
    `docir check`, so the page and the check agree about what a link is.
    """
    for token in tokens:
        if token.type != "inline" or not token.children:
            continue
        children, depth, changed = [], 0, False
        for child in token.children:
            if child.type == "link_open":
                depth += 1
            elif child.type == "link_close":
                depth -= 1
            if depth > 0:
                children.append(child)
                continue
            if child.type == "code_inline" and child.content.strip() in known:
                children.extend(_doc_link(child.content.strip(), child))
                changed = True
            elif child.type == "text" and (parts := _split_refs(child.content, known, links)):
                children.extend(parts)
                changed = True
            else:
                children.append(child)
        if changed:
            token.children = children


def _split_refs(text: str, known: frozenset[str], links: LinkIndex) -> list | None:
    """``text`` as tokens with every resolvable reference linked, else ``None``.

    ``[[...]]`` is consumed first and whole. Its brackets are dropped only when
    the target resolves to a page this site publishes; otherwise the span is
    handed on untouched, so an unresolved link stays visibly unresolved — what a
    dangling edge does on the same page, and what `docir check` reports as
    ``unresolved-link``.
    """
    out, cursor, linked = [], 0, False
    for match in WIKILINK_RE.finditer(text):
        link = parse_wikilink(match.group(1))
        if link is None:
            continue
        doc_id = links.resolve(link.target).doc_id
        if doc_id is None or doc_id not in known:
            continue
        out.extend(_plain(text[cursor : match.start()], known))
        out.extend(_wiki_link(doc_id, link, links.title(doc_id)))
        cursor, linked = match.end(), True
    if not linked:
        return _split_ids(text, known)
    out.extend(_plain(text[cursor:], known))
    return out


def _plain(text: str, known: frozenset[str]) -> list:
    """A stretch of prose outside any ``[[...]]``, with its bare ids linked."""
    if not text:
        return []
    return _split_ids(text, known) or [_text_token(text)]


def _split_ids(text: str, known: frozenset[str]) -> list | None:
    """``text`` as tokens with every known id linked, or ``None`` if none is."""
    if not known:
        return None
    out, cursor = [], 0
    for match in _DOC_ID_SHAPE.finditer(text):
        if match.group() not in known:
            continue
        if match.start() > cursor:
            out.append(_text_token(text[cursor : match.start()]))
        out.extend(_doc_link(match.group(), _code_token(match.group())))
        cursor = match.end()
    if not out:
        return None
    if cursor < len(text):
        out.append(_text_token(text[cursor:]))
    return out


def _doc_link(doc_id: str, inner: Token) -> list[Token]:
    open_token = Token("link_open", "a", 1)
    open_token.attrs = {"class": "docref", "href": page_name(doc_id)}
    return [open_token, inner, Token("link_close", "a", -1)]


def _wiki_link(doc_id: str, link: Wikilink, title: str) -> list[Token]:
    """A resolved ``[[...]]`` as an anchor whose text is the target's title.

    The title and not the target, deliberately. The slug a link was written
    against is a *stale* name the day somebody retitles the document — which is
    the failure that made these links worth resolving — so rendering the current
    title is the difference between a link that ages and one that does not. An
    explicit ``|label`` wins: whoever wrote it was making the sentence read.
    """
    href = page_name(doc_id)
    if link.section:
        href = f"{href}#{_heading_slug(link.section)}"
    open_token = Token("link_open", "a", 1)
    open_token.attrs = {"class": "wikiref", "href": href}
    return [open_token, _text_token(link.label or title or doc_id), Token("link_close", "a", -1)]


def _text_token(content: str) -> Token:
    token = Token("text", "", 0)
    token.content = content
    return token


def _code_token(content: str) -> Token:
    token = Token("code_inline", "code", 0)
    token.content = content
    return token


def _render_fence(_renderer: object, tokens: list, index: int, *_: object) -> str:
    """A code block as a titled frame: language, copy button, coloured body.

    Replaces markdown-it's own `fence`/`code_block` rules rather than
    rewriting their output, because the token still has the info string and
    the raw source — after rendering, the language is gone and the source is
    HTML that a second pass would have to un-escape to colour. Registered via
    ``add_render_rule``, which binds the renderer as the first argument.

    A ``mermaid`` fence leaves here as a figure instead: it is the one fence
    whose author meant the picture rather than the text (``infra/diagrams.py``).
    """
    token = tokens[index]
    info = getattr(token, "info", "") or ""
    if info.strip().split(" ")[0].lower() == diagrams.LANGUAGE:
        return diagrams.render_diagram(token.content)
    return (
        '<div class="codeblk"><div class="hd">'
        f"<span>{html.escape(language_label(info))}</span>"
        '<button type="button">Copy</button></div>'
        f"<pre><code>{highlight(token.content, info)}</code></pre></div>"
    )


def _level(tag: str) -> int:
    return int(tag[1:]) if tag[1:].isdigit() else 6


def _drop_leading_title(tokens: list, title: str) -> list:
    """Drop a first-line ``# Title`` that repeats the document's own title."""
    normalized = _normalize(title)
    if not normalized or len(tokens) < 3:
        return tokens
    if (
        tokens[0].type == "heading_open"
        and tokens[0].tag == "h1"
        and _normalize(tokens[1].content) == normalized
    ):
        return tokens[3:]
    return tokens


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _heading_slug(text: str) -> str:
    """The fragment id a heading gets.

    Shared with the ``[[target#heading]]`` anchor, so a prose link and the
    heading it points at cannot disagree about the spelling.
    """
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def _unique_slug(text: str, seen: dict[str, int]) -> str:
    """A stable, readable fragment id. Repeats get a numeric suffix.

    Two sections called "Context" in one document is normal; two links pointing
    at the same one is not.
    """
    base = _heading_slug(text)
    count = seen.get(base, 0)
    seen[base] = count + 1
    return base if count == 0 else f"{base}-{count}"


def _inject_anchors(rendered: str, headings: list[tuple[int, str, str]]) -> str:
    """Put a link-to-this-section marker inside each heading.

    Appended at the closing tag in document order, which is the order the slugs
    were produced in — the renderer emits headings exactly once and in sequence.
    """
    slugs = iter(slug for _, slug, _ in headings)

    def replace(match: re.Match[str]) -> str:
        slug = next(slugs, None)
        if slug is None:
            return match.group(0)
        anchor = (
            f'<a class="anchor" href="#{slug}" aria-label="link to this section">'
            f"{_ANCHOR_GLYPH}</a>"
        )
        return anchor + match.group(0)

    return _HEADING_CLOSE.sub(replace, rendered)
