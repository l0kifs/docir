"""Turning a title into a slug — the one rule three readers share.

The slug is not decoration. It is half of a document's filename, and a filename
is an address people copy: ``[[adr-…-hub-api-reads-revocation-epochs]]`` in a
body is resolved back to a document by this rule, and the published site has to
reach the same answer the ``check`` does. Two copies of it would let a link
resolve for one reader and dangle for the other — the drift
``platform.naming`` exists to prevent (adr-289e788719a7).

It lived in ``documents.domain`` while only the file store needed it. Prose
links made ``publishing`` a second reader, and ``publishing`` is a leaf that may
not import ``documents``; here both reach the same function instead.
"""

from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")

#: What a filename's slug half is truncated to. A path is typed, quoted and
#: pasted, and the id carries the identity — the slug only has to say which
#: document it is.
FILENAME_SLUG_LENGTH = 60

#: Long enough that no title is truncated. The *untruncated* slug is what
#: somebody writes when they slugify a title by hand, so it has to be a
#: resolvable form alongside the truncated one the file carries.
UNTRUNCATED = 1_000_000


def slugify(title: str, *, max_length: int = FILENAME_SLUG_LENGTH) -> str:
    """Turn a title into a lowercase, hyphen-separated slug.

    Non-alphanumeric runs collapse to a single hyphen; leading/trailing
    hyphens are stripped. Falls back to ``"untitled"`` for empty input so a
    file path can always be formed.
    """
    lowered = title.strip().lower()
    slug = _NON_ALNUM.sub("-", lowered).strip("-")
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip("-")
    return slug or "untitled"
