"""Body-edit helpers for the three ``docs update`` body modes.

These operate purely on markdown text — no I/O — so the section-manipulation
rules (append at end, replace under a heading) are unit-testable in isolation.
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
