"""Fingerprinting the ``code`` globs a document declares.

The one place that turns a pattern into evidence, shared by the two writes that
produce it — ``add`` (which mints a baseline for the globs the document is born
with) and ``update`` (which mints one for globs it gains, and re-bases every
glob a verification actually read).

Kept out of both callers because the rule it encodes is a single rule: a digest
here records *what the tree looked like*, and nothing about who looked at it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from docir.platform.filesystem.ports import CodeMatcher


def fingerprint_patterns(matcher: CodeMatcher | None, patterns: Iterable[str]) -> dict[str, str]:
    """Digest each pattern, dropping the ones that cannot be resolved.

    Two absences collapse into one answer. Without a matcher there is no tree to
    read — a global store has no repository above it — and a pattern that
    resolves to nothing has no contents to hash. Both leave the pattern out of
    the map, where every reader treats it as *unknown* rather than *unchanged*.
    """
    if matcher is None:
        return {}
    digests: dict[str, str] = {}
    for pattern in patterns:
        digest = matcher.fingerprint(pattern)
        if digest is not None:
            digests[pattern] = digest
    return digests


def mint_baseline(
    matcher: CodeMatcher | None,
    patterns: Iterable[str],
    existing: Mapping[str, str],
    *,
    verified_now: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The baseline a write leaves behind: pruned, re-based, then topped up.

    Three moves, in order, and the order is the whole rule:

    * **Prune.** A pattern the document no longer declares takes its baseline
      with it, exactly as ``verified_code`` does — a digest for a glob nobody
      governs is evidence about nothing.
    * **Re-base what was verified.** A verification read the code as it stands,
      so the two digests agree from that moment; passing them in rather than
      re-walking the tree also means a verification costs one fingerprint, not
      two.
    * **Mint only what is missing.** A pattern that already carries a baseline
      keeps it. Re-declaring a glob is not a re-reading of the code under it, so
      a mechanical ``--set-code`` must never clear a drift nobody looked at —
      the laundering adr-bd7c4f3c5764 forbids, arriving through the cheapest
      door there is. It is also what keeps the cost bounded: the tree is walked
      once per pattern per document, on the write that first names it.
    """
    kept = set(patterns)
    baseline = {pattern: digest for pattern, digest in existing.items() if pattern in kept}
    baseline.update(verified_now or {})
    missing = tuple(pattern for pattern in patterns if pattern not in baseline)
    baseline.update(fingerprint_patterns(matcher, missing))
    return baseline
