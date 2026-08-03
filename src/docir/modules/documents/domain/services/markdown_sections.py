"""Section helpers for the body-edit modes and the section read path.

These operate purely on markdown text — no I/O — so the section-manipulation
rules (append at end, replace under a heading, read one back) are unit-testable
in isolation. :func:`extract_section` and :func:`replace_section` share one
notion of where a section ends, which is what keeps ``get --section X`` and
``update --replace-section X`` talking about the same span of the file.
"""

from __future__ import annotations

import re

from docir.platform.errors import ValidationError

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def append_section(body: str, heading: str, content: str, *, level: int = 2) -> str:
    """Append a new ``level``-deep heading and content at the end of the body.

    The default, safest body edit: existing content is never touched.
    """
    prefix = "#" * level
    section = f"{prefix} {heading}\n\n{content.strip()}\n"
    base = body.rstrip()
    if base:
        return f"{base}\n\n{section}"
    return section


def replace_section(body: str, heading: str, content: str) -> str:
    """Replace the content under an existing heading, keeping the heading line.

    The heading is matched case-insensitively by its text at any level. Content
    from just after the heading up to the next heading of the same or higher
    level (i.e. equal/fewer ``#``) is replaced. Raises :class:`ValidationError`
    if no such heading exists.
    """
    lines = body.splitlines()
    target = heading.strip().lower()

    start_idx: int | None = None
    start_level = 0
    for i, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match and match.group(2).strip().lower() == target:
            start_idx = i
            start_level = len(match.group(1))
            break

    if start_idx is None:
        raise ValidationError(f"cannot replace section {heading!r}: no matching heading found")

    end_idx = len(lines)
    for j in range(start_idx + 1, len(lines)):
        match = _HEADING_RE.match(lines[j])
        if match and len(match.group(1)) <= start_level:
            end_idx = j
            break

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
    return [
        match.group(2).strip()
        for line in body.splitlines()
        if (match := _HEADING_RE.match(line)) is not None
    ]


def extract_section(body: str, heading: str) -> str:
    """Return one section — its heading line and everything under it.

    The counterpart to :func:`replace_section` and deliberately its mirror: the
    same case-insensitive heading match, the same end boundary (the next heading
    of equal or higher level), so what ``get --section X`` shows is exactly the
    span ``update --replace-section X`` would overwrite.

    Raises :class:`ValidationError` naming the headings that do exist, because
    the caller is an agent that would otherwise have to fetch the whole body to
    find out — the cost the section read path exists to avoid.
    """
    lines = body.splitlines()
    target = heading.strip().lower()

    start_idx: int | None = None
    start_level = 0
    for i, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match and match.group(2).strip().lower() == target:
            start_idx = i
            start_level = len(match.group(1))
            break

    if start_idx is None:
        available = section_headings(body)
        listed = ", ".join(repr(name) for name in available) if available else "none"
        raise ValidationError(f"no section {heading!r} in this document; available: {listed}")

    end_idx = len(lines)
    for j in range(start_idx + 1, len(lines)):
        match = _HEADING_RE.match(lines[j])
        if match and len(match.group(1)) <= start_level:
            end_idx = j
            break

    return "\n".join(lines[start_idx:end_idx]).strip() + "\n"
