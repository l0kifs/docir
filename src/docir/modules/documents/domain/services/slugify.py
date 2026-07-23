"""Derive a stable, filesystem-safe slug from a document title."""

from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(title: str, *, max_length: int = 60) -> str:
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
