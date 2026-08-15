"""Pure text transforms for materialising and merging instruction files.

No I/O — every function here takes strings and returns strings. Two file shapes
are supported:

- **Skill** (whole file): the packaged template's frontmatter is preserved and a
  version *stamp* is inserted right after it, so the Claude Code skill loader
  still sees valid frontmatter followed by a machine-parseable version marker.
- **Pointer** (a block inside ``AGENTS.md``): the skill's frontmatter
  ``description`` plus the repo-relative path to the skill file, wrapped between
  ``<!-- docir:start -->`` / ``<!-- docir:end -->`` markers. Merging *replaces
  only that block* and preserves any surrounding content, so a project's own
  ``AGENTS.md`` house-rules survive an update.

The block used to inline the whole guide, which made ``AGENTS.md`` a second copy
of a file already in the repo — the duplication that goes stale first because
nothing reads both. The description is copied rather than summarised because it
is the part that decides *whether to read further*: an assistant that never opens
the skill still has to know when it should.

The stamp is the sole persisted state: :func:`parse_version` reads it back so
``update`` can report the installed-vs-refreshed version transition.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

#: Opening marker of docir's block inside a shared file (e.g. ``AGENTS.md``).
MARK_START = "<!-- docir:start -->"
#: Closing marker of docir's block.
MARK_END = "<!-- docir:end -->"
#: Marks a block as the pointer form. Its *absence* from an existing block is
#: what identifies one written before this form existed (:func:`has_inlined_guide`).
MARK_POINTER = "<!-- docir:pointer -->"

_STAMP_RE = re.compile(r"<!-- docir:v(\S+) ")
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_BLOCK_RE = re.compile(re.escape(MARK_START) + r".*?" + re.escape(MARK_END), re.DOTALL)
# ``description:`` plus any indented continuation lines (a YAML folded scalar).
_DESCRIPTION_RE = re.compile(r"^description:[ \t]*(.*(?:\n[ \t]+\S.*)*)$", re.MULTILINE)


@dataclass(frozen=True)
class SkillPointer:
    """One skill a pointer block refers to: what it covers, and where it lives."""

    #: The skill's frontmatter ``description``, verbatim.
    description: str
    #: Install-root-relative, ``/``-separated path to the skill file.
    path: str


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


def parse_description(template: str) -> str | None:
    """Lift the ``description`` out of a skill template's frontmatter.

    ``None`` when the template has no frontmatter or no non-empty ``description``.
    The application layer turns that into an error rather than this one: the
    module's ``domain`` is a pure text transform with no dependencies at all, not
    even the error taxonomy, and reporting *absence* is the transform's answer.
    """
    frontmatter = _FRONTMATTER_RE.match(template)
    match = _DESCRIPTION_RE.search(frontmatter.group(0)) if frontmatter else None
    description = " ".join(match.group(1).split()).strip("\"'") if match else ""
    return description or None


def render_skill(template: str, version: str) -> str:
    """Produce a standalone skill file: template with the stamp after frontmatter."""
    match = _FRONTMATTER_RE.match(template)
    if match is None:
        return f"{stamp(version)}\n{template}"
    end = match.end()
    return f"{template[:end]}{stamp(version)}\n{template[end:]}"


def render_pointer(pointers: Sequence[SkillPointer], version: str) -> str:
    """Produce docir's marker-delimited block: an index of the skill files."""
    entries = "\n".join(f"- [`{p.path}`]({p.path}) — {p.description}" for p in pointers)
    body = (
        "## docir\n\n"
        "`docir` manages this project's design docs (decisions, issues, architecture).\n"
        "Its instructions live in the files linked below — open the one whose description\n"
        "matches what you are about to do, and follow it. This block is only an index.\n\n"
        f"{entries}"
    )
    return f"{MARK_START}\n{stamp(version)}\n{MARK_POINTER}\n\n{body}\n{MARK_END}"


def has_block(text: str) -> bool:
    """Whether ``text`` already contains docir's marker block."""
    return MARK_START in text and MARK_END in text


def has_inlined_guide(text: str) -> bool:
    """Whether ``text``'s docir block predates the pointer form (it inlines the guide).

    Keyed on :data:`MARK_POINTER` rather than on the guide's wording, so it stays
    right when the template changes. Used only to explain the shrinkage: an update
    that drops ~500 lines from a tracked file should say why.
    """
    match = _BLOCK_RE.search(text)
    return match is not None and MARK_POINTER not in match.group(0)


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
