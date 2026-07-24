"""Pure text transforms for materialising and merging instruction files.

No I/O — every function here takes strings and returns strings. Two file shapes
are supported:

- **Skill** (whole file): the packaged template's frontmatter is preserved and a
  version *stamp* is inserted right after it, so the Claude Code skill loader
  still sees valid frontmatter followed by a machine-parseable version marker.
- **Embedded** (a block inside ``AGENTS.md``): the template body (frontmatter
  stripped) is wrapped between ``<!-- docir:start -->`` / ``<!-- docir:end -->``
  markers. Merging *replaces only that block* and preserves any surrounding
  content, so a project's own ``AGENTS.md`` house-rules survive an update.

The stamp is the sole persisted state: :func:`parse_version` reads it back so
``update`` can report the installed-vs-refreshed version transition.
"""

from __future__ import annotations

import re

#: Opening marker of docir's block inside a shared file (e.g. ``AGENTS.md``).
MARK_START = "<!-- docir:start -->"
#: Closing marker of docir's block.
MARK_END = "<!-- docir:end -->"

_STAMP_RE = re.compile(r"<!-- docir:v(\S+) ")
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_BLOCK_RE = re.compile(re.escape(MARK_START) + r".*?" + re.escape(MARK_END), re.DOTALL)


def stamp(version: str) -> str:
    """The HTML-comment version marker written into every generated file."""
    return (
        f"<!-- docir:v{version} — generated file, do not edit by hand; "
        "refresh with `docir agent update` after upgrading docir -->"
    )


def parse_version(text: str) -> str | None:
    """Read the docir version stamped into ``text``, or ``None`` if absent."""
    match = _STAMP_RE.search(text)
    return match.group(1) if match else None


def strip_frontmatter(text: str) -> str:
    """Drop a leading ``---\\n...\\n---\\n`` YAML frontmatter block, if present."""
    return _FRONTMATTER_RE.sub("", text, count=1)


def render_skill(template: str, version: str) -> str:
    """Produce a standalone skill file: template with the stamp after frontmatter."""
    match = _FRONTMATTER_RE.match(template)
    if match is None:
        return f"{stamp(version)}\n{template}"
    end = match.end()
    return f"{template[:end]}{stamp(version)}\n{template[end:]}"


def render_block(template: str, version: str) -> str:
    """Produce docir's marker-delimited block for embedding in a shared file."""
    body = strip_frontmatter(template).strip()
    return f"{MARK_START}\n{stamp(version)}\n\n{body}\n{MARK_END}"


def has_block(text: str) -> bool:
    """Whether ``text`` already contains docir's marker block."""
    return MARK_START in text and MARK_END in text


def merge_block(existing: str | None, block: str) -> str:
    """Merge docir's ``block`` into a shared file, preserving foreign content.

    - Missing file → the block becomes the whole file.
    - File already carrying docir's markers → replace only the marked region.
    - File without markers → append the block, keeping the existing content.
    """
    if existing is None:
        return f"{block}\n"
    if has_block(existing):
        # A lambda replacement avoids ``re`` interpreting backslashes in ``block``
        # (the guide body contains ``\`` line-continuations in shell examples).
        return _BLOCK_RE.sub(lambda _match: block, existing, count=1)
    return f"{existing.rstrip()}\n\n{block}\n"
