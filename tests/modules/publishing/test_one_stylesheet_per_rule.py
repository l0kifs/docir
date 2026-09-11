"""No CSS rule is declared identically in two stylesheets.

The site has two of them — `assets.STYLES` for the document and index pages,
`graph._GRAPH_CSS` for the graph — and they used to declare thirteen rules
byte-for-byte alike: the reset, the link colour, the focus ring, the wordmark
and the top-bar controls. `theme.CSS_CHROME` holds those now, and this is what
stops them growing back.

The cost of the duplication is on record rather than hypothetical. A `.sub`
utility tuned on one side shrank the wordmark's tail on the pages but not on
the graph, whose stylesheet had no such rule — one brand, two sizes, and
nothing to say which was intended.

Rules that *differ* between the two are not findings: the graph is a
full-viewport application and the pages scroll, so `body`, `.topbar`, `.main`,
`.chip` and the two `:root` blocks each say something different on purpose.
Only identical text is duplication.
"""

from __future__ import annotations

import re

from docir.modules.publishing.infra import assets, theme
from docir.modules.publishing.infra import graph as graph_module


def _rules(css: str) -> dict[str, str]:
    """Top-level `selector -> declaration`, whitespace-normalised.

    Brace-matched rather than regex-matched on the whole rule: a naive pattern
    reads a multi-line declaration as a different rule from the same one
    written on one line, which is how an earlier count of this duplication came
    out at seven instead of thirteen.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    rules: dict[str, str] = {}
    depth, buffer, selector = 0, "", ""
    for char in css:
        if char == "{":
            depth += 1
            if depth == 1:
                selector, buffer = re.sub(r"\s+", " ", buffer).strip(), ""
            else:
                buffer += char
        elif char == "}":
            depth -= 1
            if depth == 0:
                if selector and not selector.startswith("@"):
                    rules[selector] = re.sub(r"\s+", " ", buffer).strip()
                buffer = ""
            else:
                buffer += char
        else:
            buffer += char
    return rules


def _sources() -> dict[str, dict[str, str]]:
    """The three places a rule can be written, each with its own rules only."""
    return {
        "theme.CSS_CHROME": _rules(theme.CSS_CHROME),
        "assets.STYLES": _rules(assets.STYLES.replace(theme.CSS_CHROME, "")),
        "graph._GRAPH_CSS": _rules(graph_module._GRAPH_CSS),
    }


def test_no_rule_is_written_out_twice() -> None:
    """Across all three sources, not just the two stylesheets.

    Comparing only the two page stylesheets is the version of this guard that
    does not work: once a rule moves into `CSS_CHROME`, copying it back into
    one stylesheet leaves the *other* stylesheet innocent, so the intersection
    stays empty and the check passes while the duplication is live. Verified by
    injecting exactly that.
    """
    sources = _sources()
    duplicated = []
    for name, rules in sources.items():
        for other, other_rules in sources.items():
            if other <= name:
                continue
            duplicated += [
                f"{selector} in both {name} and {other}"
                for selector in set(rules) & set(other_rules)
                if rules[selector] == other_rules[selector]
            ]
    assert not duplicated, (
        f"{sorted(duplicated)} — declare it once in theme.CSS_CHROME, which both "
        f"stylesheets already include, or make the two actually differ"
    )


def test_the_shared_block_is_still_reaching_both_pages() -> None:
    """A guard that only checks for duplication passes if the shared block is dropped.

    Both stylesheets would then declare nothing alike — because one of them
    would declare nothing at all — so the absence above has to be paired with
    the presence here.
    """
    shared = _rules(theme.CSS_CHROME)
    assert len(shared) >= 13, f"CSS_CHROME shrank to {len(shared)} rules"
    for selector, declaration in shared.items():
        assert _rules(assets.STYLES).get(selector) == declaration, (
            f"{selector} is missing from the page stylesheet"
        )
        assert _rules(theme.CSS_CHROME + graph_module._GRAPH_CSS).get(selector) == declaration, (
            f"{selector} is missing from the graph stylesheet"
        )
