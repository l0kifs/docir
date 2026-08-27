"""The oracle behind every check of docir's own prose: does this line exist?

A `docir ...` written in backticks is a line somebody will run. It appears in
the packaged guide, the README, `CLAUDE.md`, the `.claude/rules/` files, the
project store, every docstring under `src/`, the `CONTRACT.md` files — and in a
GitHub release body, which is the one surface none of docir's guards reached.

The extraction and the resolution live here, in one implementation, for the
reason `index_is_empty` is shared by `check` and `doctor`: two copies would let
a line be correct to one reader and wrong to another, and the copy that is
never wrong is the one nobody notices has stopped checking. The oracle itself
is the CLI's own command tree, introspected from `cli.app` rather than shelled
out, so a flag removed from `app.py` fails here in the same commit.

Callers:

* `tests/entry_points/test_agent_guide_matches_cli.py` — every shipped and
  in-repo surface, one case per invocation, plus the guards on this module's
  own extractors.
* `scripts/check_expressions.py` — a release body, before it is published.

Reading files is deliberately not this module's job. The test sweeps
directories that must exist and asserts they are not empty; the script takes a
path and must work with no store, no index and no network. They share the
judgement, not the input.

Resolving a line proves its *shape*. `--type decision --status open` parses,
runs, and matches nothing forever, so `_vocabulary_problems` checks that pair
too — against the shipped vocabulary rather than a store's resolved schema,
since which profiles a store enables is a local choice and whether `decision`
has an `open` status is not.
"""

from __future__ import annotations

import re

import typer.main

from docir.entry_points.cli.app import app
from docir.modules.documents.infra.profiles import PROFILE_NAMES
from docir.modules.documents.infra.schema_loader import parse_schema

#: Added by the parser at parse time, so it is on every command but on no
#: command's declared params.
_UNIVERSAL_FLAGS = frozenset({"--help"})

_FENCE = re.compile(r"^```")
_INLINE_SPAN = re.compile(r"`([^`]+)`", re.DOTALL)

#: Root flag -> does it consume the next word. Filled in by :func:`_cli_tree`
#: from the parser itself, so `--home` starts taking a value (or stops) here
#: the moment it does in `app.py`.
_ROOT_TAKES_VALUE: dict[str, bool] = {}


#: Documentation notation for "any command" / "the rest of the line". A word
#: like this in command position means the line is a shape, not an invocation,
#: so there is nothing to resolve it against. Both ellipses are here because
#: prose written for humans uses the typographic one and code blocks use the
#: ASCII one, and a checker that knows only `...` reads `…` as a value.
_PLACEHOLDER = re.compile(r"^(\.\.\.|…|<.+>)$")


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
        if path == ():
            _ROOT_TAKES_VALUE.update(
                {
                    opt: not getattr(param, "is_flag", False)
                    for param in params
                    for opt in (*param.opts, *param.secondary_opts)
                    if opt.startswith("--")
                }
            )
        children = getattr(command, "commands", {})
        if children:
            groups.add(path)
        for name, sub in children.items():
            walk(sub, (*path, name))

    walk(typer.main.get_command(app), ())
    return tree, groups


def invocations(guide: str) -> list[str]:
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

    return [part for raw in found for part in split_line(raw)]


def split_line(raw: str) -> list[str]:
    """One source line into the separate commands it shows.

    Comments go first so a `# software | research | ops` comment is not read as
    a pipeline; then command substitutions collapse to a single word, because
    the flags inside one belong to *that* program — `docir query --code $(git
    diff --name-only main)` documents `git`'s `--name-only`, not docir's; then
    `|` separates the alternatives the guide writes on one line
    (``docir archive <id> | docir unarchive <id>``).
    """
    line = re.sub(r"\s+#.*$", "", raw).strip().rstrip("\\").strip()
    line = re.sub(r"\$\(.*?\)", "SUBST", line, flags=re.DOTALL)
    return [part.strip() for part in line.split("|") if part.strip().startswith("docir")]


def _tokens(invocation: str) -> list[str]:
    """Words of an invocation, with the guide's placeholder syntax removed.

    `[--changed]` marks an optional flag and `<id>` a value the reader supplies;
    both are documentation notation, not shell syntax.
    """
    return [token.strip("[]").strip() for token in invocation.split() if token.strip("[]").strip()]


def _peel_globals(body: list[str]) -> list[str]:
    """Drop the root's own flags, which are written *before* the command.

    `docir --pretty get <id>` and `docir --home /tmp/store init` are both real
    invocations; a resolver that stopped at the first `-` attributed `--pretty`
    to `get`, which does not have it. Only a leading run is peeled, so a global
    written *after* the command — where the parser would reject it — still
    fails.
    """
    while body and body[0].split("=")[0] in _ROOT_TAKES_VALUE:
        flag = body.pop(0)
        if _ROOT_TAKES_VALUE[flag.split("=")[0]] and "=" not in flag and body:
            body.pop(0)  # the value it consumes
    return body


def _resolve(tokens: list[str]) -> list[tuple[str, ...]] | None:
    """Every command path ``tokens`` names; None if a word is bogus.

    Consumption stops at the first leaf: `docir tag rm auth` resolves to
    ('tag', 'rm') and leaves `auth` as the argument it is. A word in a *group's*
    subcommand position must exist, though — an earlier version returned the
    parent group instead, so `docir schema dump` validated happily against
    `docir schema` and a typo'd subcommand was invisible.

    A slash is the docs' shorthand for alternatives, and it appears at *any*
    depth — `docir context/get/search` at the top, `docir agent install/update`
    one level down. Every branch must resolve, and the caller checks the
    invocation's flags against each resulting path, so an alternative that only
    one branch supports is caught.

    An empty list means the line is notation rather than an invocation
    (`docir <command> ...`): there is nothing to resolve and nothing to assert.
    """
    paths: list[tuple[str, ...]] = [()]
    for token in tokens:
        if token.startswith("-"):
            break
        if _PLACEHOLDER.match(token) and any(path in GROUPS for path in paths):
            return []
        nxt: list[tuple[str, ...]] = []
        for path in paths:
            if path not in GROUPS:  # a leaf command: the rest are its arguments
                nxt.append(path)
                continue
            for alternative in token.split("/"):
                candidate = (*path, alternative)
                if candidate not in TREE:
                    return None
                nxt.append(candidate)
        paths = nxt
    return paths


def _flag_values(body: list[str], flag: str) -> list[str]:
    """The values given to a repeatable flag, in `--flag v` and `--flag=v` form.

    Placeholders are dropped rather than reported: `--type <t>` is the shape of
    the argument, not a claim about which types exist.
    """
    values: list[str] = []
    for index, token in enumerate(body):
        if token.startswith(f"{flag}="):
            values.append(token.split("=", 1)[1])
        elif token == flag and index + 1 < len(body):
            values.append(body[index + 1])
    return [
        value.strip("\"'")
        for value in values
        if not value.startswith("-") and not _PLACEHOLDER.match(value)
    ]


def _vocabulary_problems(body: list[str], invocation: str) -> list[str]:
    """`--type` / `--status` values, checked against the shipped vocabulary.

    The oracle is the core merged with **every** bundled profile, not the
    schema this store resolved. The question a document raises is "is this pair
    coherent in docir's vocabulary", and an example may legitimately reach for
    a `test_plan` from the qa profile that this repository does not enable.
    What it may not do is pair a type with a status that type never declares —
    `--type decision --status open` reads as an ordinary filter and matches
    nothing, forever, because `decision` goes proposed -> accepted.

    Without a `--type` to scope it, a status only has to be one some type
    declares: `update <id> --status resolved` names no type and cannot.
    """
    problems = []
    types = _flag_values(body, "--type")
    for name in types:
        if name not in TYPE_STATUSES:
            problems.append(
                f"unknown type {name!r} "
                f"(known: {', '.join(sorted(TYPE_STATUSES))}) — in: {invocation}"
            )

    declared = frozenset().union(
        *(TYPE_STATUSES[name] for name in types if name in TYPE_STATUSES)
    ) or (ALL_STATUSES if not types else frozenset())

    scope = f"type {', '.join(types)}" if types else "any type"
    problems.extend(
        f"status {status!r} is not declared by {scope} "
        f"(declared: {', '.join(sorted(declared))}) — in: {invocation}"
        for status in _flag_values(body, "--status")
        if status not in declared
    )
    return problems


def problems(invocation: str) -> list[str]:
    """Everything wrong with one invocation; empty when it is a real command.

    One implementation for every source, so the packaged guide and a document
    in the store cannot be judged by different rules.
    """
    tokens = _tokens(invocation)
    if not tokens or tokens[0] != "docir":
        return [f"not a docir invocation: {invocation}"]

    body = _peel_globals(tokens[1:])
    paths = _resolve(body)
    if paths is None:
        named = " ".join(t for t in body if not t.startswith("-")) or "<nothing>"
        return [f"unknown command: `docir {named}` — in: {invocation}"]

    flags = [t.split("=")[0] for t in body if t.startswith("--")]
    unknown = [
        f"`docir {' '.join(path)}` has no {flag} "
        f"(known: {', '.join(sorted(TREE[path]))}) — in: {invocation}"
        for path in paths
        for flag in flags
        if flag not in TREE[path]
    ]
    # A bogus flag name makes its value meaningless, so do not also report it.
    return unknown or _vocabulary_problems(body, invocation)


def _shipped_vocabulary() -> tuple[dict[str, frozenset[str]], frozenset[str]]:
    """Every type docir ships and the statuses each declares.

    Built from the core plus *all* bundled profiles rather than from this
    store's `docs-schema.yaml`: which profiles a store enables is a local
    choice, but whether `decision` has an `open` status is not.
    """
    schema = parse_schema({"profiles": list(PROFILE_NAMES)})
    statuses = {name: frozenset(t.statuses) for name, t in schema.types.items()}
    return statuses, frozenset().union(*statuses.values())


TREE, GROUPS = _cli_tree()
TYPE_STATUSES, ALL_STATUSES = _shipped_vocabulary()


#: Invocations that name a command on purpose *because it does not exist*.
#: Every entry is a decision record arguing against a verb, an issue proposing
#: one, or a log of the defect that motivated this very test — prose that would
#: be wrong to "fix". Keyed by the leading words, mapped to why.
#:
#: This list may only shrink by a command shipping. It is not the place to park
#: a genuine mistake: a document that tells a reader to *run* something takes
#: the fix, not an entry here. `test_every_exemption_is_still_needed` fails when
#: an entry stops matching anything, so a shipped command cannot leave its
#: exemption behind to shadow the real thing.
DELIBERATELY_UNREAL: dict[tuple[str, ...], str] = {
    ("upgrade",): "adr-31aa7aa60d11 rejects the bare verb; it shipped as `self upgrade`",
    ("serve",): "adr-a343140d72e2 weighs and rejects a live browser UI",
    ("schema", "accept"): "adr-bd3a820cc57a rejects an acknowledge-the-drift verb",
    ("schema", "add-type"): "adr-c0ce6f347f3e rejects writing the schema through the CLI",
    ("schema", "diff"): "issue-3678c897295f proposes it; still open",
    ("import",): "the bulk import repeatedly proposed and repeatedly rejected",
    ("repair",): "the name of the gap `check --fix` closed, quoted in the issues that closed it",
    ("accept-schema",): "run-f4a756206fe0 records that this verb deliberately does not exist",
    ("reindex", "--all"): "the flag that never existed — the defect issue-87a27629f6a6 is about",
    ("reindex", "--embeddings"): "adr-6a4718fa7a7d retires it; it and issue-b24e14474820 name it",
}


def exemption(invocation: str) -> tuple[str, ...] | None:
    """The exemption covering ``invocation``, if any."""
    tokens = tuple(_peel_globals(_tokens(invocation)[1:]))
    return next(
        (key for key in DELIBERATELY_UNREAL if tokens[: len(key)] == key),
        None,
    )


#: Names the binary has answered to before. A retired one is worse than a typo:
#: `docs check --strict` is a plausible-looking line that resolves to nothing on
#: any machine, and it survives every check above because the extractor is
#: anchored on `docir `. The architecture document carried 96 of them.
_RETIRED_BINARIES = frozenset({"docs"})

_RETIRED_INVOCATION = re.compile(rf"`({'|'.join(sorted(_RETIRED_BINARIES))}) ([a-z][a-z-]*)")


def retired_binary_hits(text: str) -> list[str]:
    """Spans invoking a former binary name with a word that is a real command.

    Requiring the second word to be a live subcommand is what keeps `docs/` and
    `docs-schema.yaml` out (no space) and English plurals too: "the docs query
    the index" is prose, and prose is not in backticks.
    """
    return [
        f"{binary} {word}" for binary, word in _RETIRED_INVOCATION.findall(text) if (word,) in TREE
    ]
