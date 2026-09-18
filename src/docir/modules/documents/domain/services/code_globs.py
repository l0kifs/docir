"""Matching a path against the ``code`` globs a document declares.

The Tier 1 check asks the filesystem a different question — "does this pattern
still name anything?" — and `Path.glob` answers it. This module answers the
reverse one, "does this *path* fall under this pattern", and deliberately does
not touch the filesystem: the query exists to answer "which decisions govern the
files this branch touched", and a branch that **deletes** a file is exactly when
the decisions governing it must be re-read. A filesystem-backed match would
return nothing for precisely that case.

The grammar is the one `pathlib` globbing uses, so a pattern means the same
thing to `docir check` and to `docir query --code`:

* ``**`` as a whole segment matches zero or more path segments,
* ``*`` and ``?`` match within one segment only (never across ``/``),
* ``[...]`` is a character class (``[!...]`` negates it),
* everything else is literal.

A leading ``./`` is noise on either side and is dropped. A leading **dot that is
part of a name** is not: ``.github/workflows`` is that directory and nothing
else.

A document that governs a directory governs what is inside it, so a path also
matches when any of its **ancestors** does: ``src/auth`` covers
``src/auth/login.py``. This query is how someone finds the decisions they should
read before editing a file, and a miss there is far more expensive than one
extra document to glance at.
"""

from __future__ import annotations

import re
from functools import lru_cache

_SEGMENT_ANY = "[^/]*"
_SEGMENT_ONE = "[^/]"


def _translate_segment(segment: str) -> str:
    """One path segment of a glob as a regex fragment (no ``/`` may match)."""
    out: list[str] = []
    index = 0
    while index < len(segment):
        char = segment[index]
        if char == "*":
            out.append(_SEGMENT_ANY)
        elif char == "?":
            out.append(_SEGMENT_ONE)
        elif char == "[":
            closing = segment.find("]", index + 1)
            if closing == -1:
                # An unclosed class is a literal '[', which is what a shell and
                # `fnmatch` both do. A pattern is user text; it must not raise.
                out.append(re.escape(char))
            else:
                body = segment[index + 1 : closing]
                negated = body.startswith("!")
                if negated:
                    body = "^" + body[1:]
                out.append(f"[{body}]")
                index = closing
        else:
            out.append(re.escape(char))
        index += 1
    return "".join(out)


@lru_cache(maxsize=512)
def _compiled(pattern: str) -> re.Pattern[str]:
    """``pattern`` as an anchored regex over a whole relative path.

    ``pattern`` arrives from :func:`matches` already normalized, so the cache is
    keyed on the one spelling rather than on however it was typed.

    Cached because a query matches every document's patterns against every path
    given, and the pattern set of a corpus is small and repetitive.
    """
    segments = pattern.split("/")
    # A trailing `**` is "this directory, and everything under it" — the way
    # `Path.glob` reads it — so it is peeled off first: written as a segment in
    # the loop below it would demand a trailing separator and match neither.
    trailing_any = segments[-1] == "**"
    if trailing_any:
        segments = segments[:-1]
    if not segments:
        return re.compile("^.*$")  # a bare `**` governs the whole tree

    parts: list[str] = []
    for segment in segments:
        if segment == "**":
            # Zero or more whole segments, each with its separator, so
            # `**/*.py` covers a top-level `main.py` as well as `a/b/main.py`.
            parts.append("(?:[^/]+/)*")
        else:
            parts.append(_translate_segment(segment) + "/")
    joined = "".join(parts)
    if joined.endswith("/"):
        # Each normal segment carries its trailing separator; drop the last so
        # the regex anchors at the end of the path.
        joined = joined[:-1]
    suffix = "(?:/.*)?" if trailing_any else ""
    return re.compile(f"^{joined}{suffix}$")


def _normalize(value: str) -> str:
    """A pattern or a path reduced to one spelling: no surrounding blanks, no
    leading ``./``, no surrounding ``/``.

    **Both sides go through this**, which is the fix for issue-325742d96896.
    The path used to be trimmed with ``lstrip("./")``, and ``lstrip`` takes a
    *character set*, not a prefix — so it ate the leading dot of every dotted
    path while the pattern kept its own, and the two could never meet. A
    document governing ``.github/workflows/**`` was unreachable from the file it
    named, and no guard saw it: ``check`` resolves patterns through the
    tree-walking matcher in ``platform/filesystem``, so only this text query was
    blind, and its own tests all used ``src/`` paths.
    """
    trimmed = value.strip()
    while trimmed.startswith("./"):
        trimmed = trimmed[2:]
    return trimmed.strip("/")


def matches(pattern: str, path: str) -> bool:
    """Whether ``path`` — or a directory containing it — falls under ``pattern``."""
    normalized = _normalize(path)
    cleaned = _normalize(pattern)
    if not normalized or not cleaned:
        return False
    regex = _compiled(cleaned)
    segments = normalized.split("/")
    # The path itself first, then each ancestor: a document governing a
    # directory governs the files under it, and the exact hit is the common
    # case, so it is tried before the walk up.
    return any(regex.match("/".join(segments[:cut])) for cut in range(len(segments), 0, -1))


def governs_any(patterns: tuple[str, ...], paths: tuple[str, ...]) -> bool:
    """Whether any declared pattern covers any of the queried paths."""
    return any(matches(pattern, path) for pattern in patterns for path in paths)
