"""Shared name grammars — rules about the *shape* of a key, not its meaning.

A tag key is minted by the ``tags`` module and validated again by ``documents``
(the Tier 1 ``tag-key-format`` check reads the registry). Neither module may
import the other, so the grammar lives here rather than being written twice:
two copies of a regex are two definitions waiting to disagree, and the whole
point of a controlled vocabulary is that there is one rule.

The document-id grammar is here for the same reason and one more: ``documents``
mints and validates ids, while ``platform.persistence`` has to *recognise* them
inside a body to derive the mention graph. One pattern, two readers — a second
copy would let a document be addressable by one and invisible to the other.

Pure: no I/O, no dependencies, safe for a ``domain`` layer to import (see
adr-289e788719a7).
"""

from __future__ import annotations

import re
from collections.abc import Collection
from functools import lru_cache

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


#: The document-id grammar: a lowercase type prefix, a hyphen, then a hex
#: suffix — four or more characters, which covers a zero-padded counter
#: (``adr-0007``, digits being a subset of hex) and a random token
#: (``adr-3f9a2b1c7d4e``) with one rule. Unanchored, so the same pattern can be
#: matched against a whole id or searched for inside prose.
DOC_ID_PATTERN = r"(?P<prefix>[a-z][a-z0-9]*)-(?P<suffix>[0-9a-f]{4,})"

#: The anchored form: does this string consist of exactly one id?
DOC_ID_RE = re.compile(rf"^{DOC_ID_PATTERN}$")


@lru_cache(maxsize=8)
def _mention_re(prefixes: frozenset[str]) -> re.Pattern[str] | None:
    """Compile a scanner for exactly these type prefixes.

    Built from the *schema's* prefixes rather than from
    :data:`DOC_ID_PATTERN` alone, whose prefix part is any lowercase word: left
    open, ``sha-1beef`` in a sentence about hashing would read as a document id.
    Restricting it to the prefixes a store actually declares is what makes the
    scan safe to run over free text.

    Cached because a rebuild scans every body in the corpus against the same
    prefix set, and ``None`` when there are no prefixes at all — a store with no
    types cannot be mentioning anything, and an empty alternation would compile
    to a pattern matching the empty string.
    """
    if not prefixes:
        return None
    # Longest first, so a prefix that begins with another (`ref` / `refx`)
    # cannot shadow it. The engine would backtrack to the right answer anyway;
    # this makes it true by construction rather than by trusting the backtrack.
    alternatives = "|".join(re.escape(p) for p in sorted(prefixes, key=lambda p: (-len(p), p)))
    return re.compile(rf"\b(?:{alternatives})-[0-9a-f]{{4,}}\b")


def scan_document_ids(text: str, prefixes: Collection[str]) -> tuple[str, ...]:
    """Every document id ``text`` names, deduplicated and sorted.

    Sorted rather than in order of appearance: the result is a *set* of edges,
    and a stable order keeps a rebuild from rewriting rows that did not change.

    Deliberately scans the whole text, fenced code blocks included. A body that
    shows ``docir get adr-1cfb1b212237`` in an example is naming that document
    as surely as a sentence would — the heading scanner has to treat a fence as
    opaque because a ``##`` inside one is not a heading, but an id inside one is
    still an id.

    This finds *candidates*. Whether an id resolves to a document is the
    index's question and is asked on read, so a body may name something that
    does not exist yet: an ADR routinely references the issue it will produce,
    and that mention has to start resolving when the issue is written, not when
    somebody remembers to re-save the ADR.
    """
    pattern = _mention_re(frozenset(prefixes))
    if pattern is None:
        return ()
    return tuple(sorted(set(pattern.findall(text))))
