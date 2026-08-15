"""Section helpers for the body-edit modes and the section read path.

These operate purely on markdown text — no I/O — so the section-manipulation
rules (append at end, replace under a heading, read one back) are unit-testable
in isolation. :func:`extract_section` and :func:`replace_section` share one
notion of where a section ends, which is what keeps ``get --section X`` and
``update --replace-section X`` talking about the same span of the file.

That span is located with :func:`~.markdown_headings.scan_headings`, the same
scanner :mod:`chunking` splits on — so a heading quoted inside a fenced block is
not a section here either (issue-af046a467575).
"""

from __future__ import annotations

from docir.modules.documents.domain.services.markdown_headings import scan_headings
from docir.platform.errors import ValidationError


def _reject_own_markers(heading: str) -> None:
    """Refuse a heading argument that already carries its own ``#`` markers.

    The caller names a heading by its *text*; the level is written here. Passing
    the line as it appears in the file — ``"## Resolution"`` — used to be
    accepted and produced ``## ## Resolution``, which no section-edit mode can
    repair: ``replace_section`` keeps the heading line by contract and appending
    again adds a sibling, so the only way out was ``--replace-body --force``.
    The safest body edit must not be the one that reaches a state only the
    riskiest one can leave (issue-d5f68b44b1d9).

    Stripping the markers instead would look friendlier and be worse: it makes
    ``"### Notes"`` silently mean level 2, guessing at an intent the caller
    stated.
    """
    if heading.lstrip().startswith("#"):
        text = heading.lstrip("# ").strip()
        raise ValidationError(
            f"heading {heading!r} carries its own '#' markers: name the heading by its "
            f"text alone (here, {text!r}) — the level is written for you"
        )


def append_section(body: str, heading: str, content: str, *, level: int = 2) -> str:
    """Append a new ``level``-deep heading and content at the end of the body.

    The default, safest body edit: existing content is never touched.
    """
    _reject_own_markers(heading)
    prefix = "#" * level
    section = f"{prefix} {heading}\n\n{content.strip()}\n"
    base = body.rstrip()
    if base:
        return f"{base}\n\n{section}"
    return section


def _locate_section(body: str, heading: str) -> tuple[list[str], int, int]:
    """Find a heading by text; return the body's lines, its index and its level.

    Shared by :func:`replace_section` and :func:`extract_section` so the two
    cannot drift on what counts as a match — an agent that reads one span and
    overwrites another is the failure this module exists to prevent. The miss
    is reported the same way for both, naming the headings that do exist: a
    caller who passed ``"## Resolution"`` for a section written as
    ``## Resolution`` sees ``'Resolution'`` in the list and needs no second
    round trip to work out why.
    """
    lines = body.splitlines()
    target = heading.strip().lower()
    for found in scan_headings(body):
        if found.text.lower() == target:
            return lines, found.line, found.level

    available = section_headings(body)
    listed = ", ".join(repr(name) for name in available) if available else "none"
    raise ValidationError(f"no section {heading!r} in this document; available: {listed}")


def _section_end(body: str, lines: list[str], start_idx: int, start_level: int) -> int:
    """The line index where a section ends: the next heading of equal/higher level.

    A heading inside a fenced block is not one, so a section that quotes a
    markdown template runs past it to the real boundary. Ending the span early
    is what let ``replace_section`` strand the rest of the quote at top level.
    """
    for found in scan_headings(body):
        if found.line > start_idx and found.level <= start_level:
            return found.line
    return len(lines)


def replace_section(body: str, heading: str, content: str) -> str:
    """Replace the content under an existing heading, keeping the heading line.

    The heading is matched case-insensitively by its text at any level. Content
    from just after the heading up to the next heading of the same or higher
    level (i.e. equal/fewer ``#``) is replaced. Raises :class:`ValidationError`
    if no such heading exists.
    """
    lines, start_idx, start_level = _locate_section(body, heading)
    end_idx = _section_end(body, lines, start_idx, start_level)

    new_lines = [
        *lines[: start_idx + 1],
        "",
        content.strip(),
        "",
        *lines[end_idx:],
    ]
    return "\n".join(new_lines).rstrip() + "\n"


def section_headings(body: str) -> list[str]:
    """Every heading in ``body``, in order, at any level.

    Used to tell a caller what they *could* have asked for when the section they
    named does not exist — a "no such section" error that does not list the real
    ones just moves the search into another round trip.
    """
    return [found.text for found in scan_headings(body)]


def extract_section(body: str, heading: str) -> str:
    """Return one section — its heading line and everything under it.

    The counterpart to :func:`replace_section` and deliberately its mirror: the
    same case-insensitive heading match, the same end boundary (the next heading
    of equal or higher level), so what ``get --section X`` shows is exactly the
    span ``update --replace-section X`` would overwrite.

    Raises :class:`ValidationError` naming the headings that do exist, because
    the caller is an agent that would otherwise have to fetch the whole body to
    find out — the cost the section read path exists to avoid.

    The ``#``-marker guard on :func:`append_section` deliberately does *not*
    apply here. Reading corrupts nothing, hand-editing markdown is permitted, so
    a file that already carries a doubled marker must stay readable — that is
    how someone finds it and repairs it.
    """
    lines, start_idx, start_level = _locate_section(body, heading)
    end_idx = _section_end(body, lines, start_idx, start_level)
    return "\n".join(lines[start_idx:end_idx]).strip() + "\n"
