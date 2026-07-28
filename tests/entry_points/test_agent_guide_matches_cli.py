"""Every `docir ...` command in the packaged agent guide must exist in the CLI.

Guards GAP-040. The guide (`modules/agents/infra/templates/skill.md`) is the one
artifact `docir agent install` copies into *other* repositories, so a wrong
instruction there is distributed to every adopting project and is executed by an
agent that has no way to know better. It told agents to run `docir reindex
--all` — a flag that has never existed — at the single most important recovery
step ("after any merge/pull"). Nothing checked the guide against the CLI it
documents, so the error survived until a human happened to run the line.

The oracle is the CLI's own command tree, introspected rather than shelled out:
the same object `docir --help` prints from, so the test cannot drift from the
binary. A flag removed from `app.py` fails here in the same commit.

Extraction is deliberately strict. Anything inside a fenced code block or an
inline code span that begins with `docir ` is treated as an invocation and must
resolve. Prose that names a command therefore has to be written as prose (an
agent will try to run a backticked command regardless of the surrounding
sentence, which is the failure this guards). Product-name mentions — `~/.docir`,
"docir keeps docs in one store" — are not code spans and are not extracted.
"""

from __future__ import annotations

import re

import pytest
import typer.main

from docir.entry_points.cli.app import app
from docir.modules.agents.infra.template_provider import PackagedTemplateProvider

#: Added by the parser at parse time, so it is on every command but on no
#: command's declared params.
_UNIVERSAL_FLAGS = frozenset({"--help"})

_FENCE = re.compile(r"^```")
_INLINE_SPAN = re.compile(r"`([^`]+)`", re.DOTALL)


def _cli_tree() -> tuple[dict[tuple[str, ...], set[str]], set[tuple[str, ...]]]:
    """Command path -> its long flags, plus the set of paths that are groups.

    Groups matter for resolution: after `docir schema` the next word *must* be a
    subcommand, while after `docir get` it is the document id.
    """
    tree: dict[tuple[str, ...], set[str]] = {}
    groups: set[tuple[str, ...]] = set()

    def walk(command: object, path: tuple[str, ...]) -> None:
        params = getattr(command, "params", [])
        tree[path] = {
            opt
            for param in params
            for opt in (*param.opts, *param.secondary_opts)
            if opt.startswith("--")
        } | set(_UNIVERSAL_FLAGS)
        children = getattr(command, "commands", {})
        if children:
            groups.add(path)
        for name, sub in children.items():
            walk(sub, (*path, name))

    walk(typer.main.get_command(app), ())
    return tree, groups


def _invocations(guide: str) -> list[str]:
    """Every `docir ...` line the guide presents as runnable.

    Two sources, because the guide uses both: lines inside fenced blocks, and
    inline code spans (which may wrap across a source line, e.g. ``**`docir
    init`**``, so spans are whitespace-normalized).

    The prose is separated from the fenced blocks *before* the inline-span regex
    runs, because a ``` fence is itself backticks: pairing them across the whole
    document silently swallows each block into one giant "span" and shifts every
    pair after it, which made an earlier version of this test extract 28
    invocations while missing the exact line it exists to catch.
    """
    found: list[str] = []
    prose: list[str] = []

    in_fence = False
    for line in guide.splitlines():
        if _FENCE.match(line.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            if line.strip().startswith("docir "):
                found.append(line)
        else:
            prose.append(line)

    for span in _INLINE_SPAN.findall("\n".join(prose)):
        normalized = " ".join(span.split())
        if normalized.startswith("docir "):
            found.append(normalized)

    return [part for raw in found for part in _split(raw)]


def _split(raw: str) -> list[str]:
    """One source line into the separate commands it shows.

    Comments go first so a `# software | research | ops` comment is not read as
    a pipeline, then `|` separates the alternatives the guide writes on one line
    (``docir archive <id> | docir unarchive <id>``).
    """
    line = re.sub(r"\s+#.*$", "", raw).strip().rstrip("\\").strip()
    return [part.strip() for part in line.split("|") if part.strip().startswith("docir")]


def _tokens(invocation: str) -> list[str]:
    """Words of an invocation, with the guide's placeholder syntax removed.

    `[--changed]` marks an optional flag and `<id>` a value the reader supplies;
    both are documentation notation, not shell syntax.
    """
    return [token.strip("[]").strip() for token in invocation.split() if token.strip("[]").strip()]


def _resolve(tokens: list[str]) -> tuple[str, ...] | None:
    """Longest command path at the head of ``tokens``; None if a word is bogus.

    Consumption stops at the first leaf: `docir tag rm auth` resolves to
    ('tag', 'rm') and leaves `auth` as the argument it is. A word in a *group's*
    subcommand position must exist, though — an earlier version returned the
    parent group instead, so `docir schema dump` validated happily against
    `docir schema` and a typo'd subcommand was invisible.
    """
    path: tuple[str, ...] = ()
    for token in tokens:
        if token.startswith("-"):
            break
        if path not in GROUPS:  # a leaf command: the rest are its arguments
            break
        candidate = (*path, token)
        if candidate not in TREE:
            return None
        path = candidate
    return path


GUIDE = PackagedTemplateProvider().skill_template()
TREE, GROUPS = _cli_tree()
INVOCATIONS = _invocations(GUIDE)


@pytest.mark.parametrize(
    "expected",
    [
        "docir reindex",  # the line GAP-040 was actually wrong on
        "docir check --fix",
        "docir add --type decision",
        "docir tag rm auth",
        "docir context",
        "docir schema validate",
    ],
)
def test_the_extractor_finds_known_invocations(expected: str) -> None:
    """Guard the guard — an extractor that finds nothing passes everything.

    The first version of this test asserted only a *count*, and still reported
    28 invocations while dropping the one line the whole test exists for. A
    count cannot tell you *which* lines were missed; these names can. Each entry
    is a line that must be reachable from a different part of the document —
    fenced block, inline span, table cell, indented sub-list block.
    """
    assert any(inv.startswith(expected) for inv in INVOCATIONS), (
        f"extractor no longer finds {expected!r} — it is silently under-checking"
    )


@pytest.mark.parametrize("invocation", INVOCATIONS, ids=lambda inv: inv[:60])
def test_invocation_exists_in_the_cli(invocation: str) -> None:
    tokens = _tokens(invocation)
    assert tokens[0] == "docir"
    body = tokens[1:]

    # `docir` alone ("prefix all commands with `docir`") names the binary and
    # asserts nothing about a subcommand.
    subcommands = [token for token in body if not token.startswith("-")]
    if not subcommands:
        return

    # The guide writes related commands as a slash list in prose
    # (`docir context/get/search/query`); each alternative must be real.
    for alternative in subcommands[0].split("/"):
        path = _resolve([alternative, *body[1:]])
        assert path, f"unknown command: `docir {alternative}` — in: {invocation}"

        known = TREE[path]
        for flag in (t.split("=")[0] for t in body if t.startswith("--")):
            assert flag in known, (
                f"`docir {' '.join(path)}` has no {flag} "
                f"(known: {', '.join(sorted(known))}) — in: {invocation}"
            )
