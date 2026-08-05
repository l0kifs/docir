"""Shared name grammars — rules about the *shape* of a key, not its meaning.

A tag key is minted by the ``tags`` module and validated again by ``documents``
(the Tier 1 ``tag-key-format`` check reads the registry). Neither module may
import the other, so the grammar lives here rather than being written twice:
two copies of a regex are two definitions waiting to disagree, and the whole
point of a controlled vocabulary is that there is one rule.

Pure: no I/O, no dependencies, safe for a ``domain`` layer to import (see
adr-289e788719a7).
"""

from __future__ import annotations

import re

#: The tag-key grammar: lowercase, starts with a letter, then letters, digits or
#: hyphens. Deliberately narrow — the point of a controlled vocabulary is that
#: `auth`, `Auth` and `AUTH` cannot all exist, and a key ends up in file
#: frontmatter, in a CLI flag and in a YAML registry, so it has to survive all
#: three without quoting.
TAG_KEY_PATTERN = r"^[a-z][a-z0-9-]*$"
TAG_KEY_RE = re.compile(TAG_KEY_PATTERN)

#: Human-readable form of the same rule, for error messages and check findings.
TAG_KEY_RULE = "lowercase letters, digits and hyphens, starting with a letter"


def is_valid_tag_key(key: str) -> bool:
    """Whether ``key`` matches the tag-key grammar.

    Read paths must never call this to *reject* — a store written before the
    rule existed can hold keys that fail it, and refusing to load them would
    make an old corpus unreadable rather than merely untidy. Rejection belongs
    on the write path (`tag add`, `tag rename`); everything already on disk is
    reported by `docir check` as a warning instead.
    """
    return bool(TAG_KEY_RE.match(key))
