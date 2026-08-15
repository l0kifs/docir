"""Every `docir ...` command in docir's own prose must exist in the CLI.

Guards issue-87a27629f6a6. The guide (`modules/agents/infra/templates/skill.md`) is the one
artifact `docir agent install` copies into *other* repositories, so a wrong
instruction there is distributed to every adopting project and is executed by an
agent that has no way to know better. It told agents to run `docir reindex
--all` — a flag that has never existed — at the single most important recovery
step ("after any merge/pull"). Nothing checked the guide against the CLI it
documents, so the error survived until a human happened to run the line.

The oracle is the CLI's own command tree, introspected rather than shelled out:
the same object `docir --help` prints from, so the test cannot drift from the
binary. A flag removed from `app.py` fails here in the same commit.

Five sources are checked, because the same rot reaches all of them and only the
first was covered. The guide and the README are what an *adopter* reads;
`CLAUDE.md` and the project store (`.docir/docs/**`) are what an agent working
*in this repo* reads, and CLAUDE.md points at the store first; docstrings under
`src/` are what a reader reaches by following the code. The second group went
unchecked long enough for the architecture document to accumulate 96 invocations
of the binary's previous name beside `--set-field` and `reindex --all`, and the
third kept 37 more after the markdown side was already clean.

Extraction is deliberately strict. Anything inside a fenced code block or an
inline code span that begins with `docir ` is treated as an invocation and must
resolve. Prose that names a command therefore has to be written as prose (an
agent will try to run a backticked command regardless of the surrounding
sentence, which is the failure this guards). Product-name mentions — `~/.docir`,
"docir keeps docs in one store" — are not code spans and are not extracted.

A retired binary name needs its own check rather than falling out of this one:
a span opening with the old name does not start with `docir `, so the extractor
never saw it and every one of those 96 lines read as "nothing to validate".

`--type` and `--status` values are checked too, against the core merged with
every bundled profile. Resolving a command proves the *shape* of a line and
nothing about its meaning: `--type decision --status open` parses, runs, and
matches nothing forever, because `decision` goes proposed -> accepted. The
oracle is the shipped vocabulary rather than this store's resolved schema,
so an example may reach for a type from a profile this repository does not
enable. Other values stay unchecked — a tag, an id, a heading — because each
is a fact about one corpus rather than about docir.
"""

from __future__ import annotations

import pathlib
import re

import pytest
import typer.main

from docir.entry_points.cli.app import app
from docir.modules.agents.infra.template_provider import PackagedTemplateProvider
from docir.modules.documents.infra.profiles import PROFILE_NAMES
from docir.modules.documents.infra.schema_loader import parse_schema

_REPO = pathlib.Path(__file__).resolve().parents[2]

#: docir's own front door. It goes stale the same way the packaged guide
#: does and is the first thing an adopter reads.
_README = (_REPO / "README.md").read_text(encoding="utf-8")

#: The repo-local store. docir documents itself in docir, so these files are
#: the working instructions for anyone (human or agent) changing this codebase,
#: and CLAUDE.md sends readers to them before it explains anything itself.
_STORE_DOCS = _REPO / ".docir" / "docs"

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


def _problems(invocation: str) -> list[str]:
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


GUIDE = PackagedTemplateProvider().skill_template()
TREE, GROUPS = _cli_tree()
TYPE_STATUSES, ALL_STATUSES = _shipped_vocabulary()
INVOCATIONS = _invocations(GUIDE)


@pytest.mark.parametrize(
    "expected",
    [
        "docir reindex",  # the line issue-87a27629f6a6 was actually wrong on
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
    assert not _problems(invocation), "\n".join(_problems(invocation))


#: Commands whose *unset* flags produce output that is silently wrong rather
#: than absent, so the docs have to name every one of them.
#:
#: `build` is the only member today. A site published without `--title` is
#: headed "Documentation" in its heading, its browser tab and beside its mark;
#: without `--logo` it wears docir's; without `--include-archived` it quietly
#: omits documents. Nothing errors, nobody is prompted, and the reader has no
#: way to tell the result from an intended one — so an undocumented flag here
#: is a wrong artifact distributed to everyone who reads the site.
_MUST_DOCUMENT_EVERY_FLAG = [("build",)]

#: The root command's own flags — how to talk to the store (`--home`,
#: `--no-daemon`) and how to print (`--json`, `--pretty`, `--no-trim`), plus
#: `--help`. They are about the invocation, not about what a command produces,
#: and the README documents them once in their own paragraph rather than under
#: every command. Read off the CLI instead of listed here, so a new global flag
#: is excluded without anyone remembering to come back.
_GLOBAL_FLAGS = TREE[()]


@pytest.mark.parametrize("path", _MUST_DOCUMENT_EVERY_FLAG, ids=lambda p: " ".join(p))
@pytest.mark.parametrize("doc", ["guide", "readme"])
def test_the_docs_name_every_flag_that_shapes_the_output(doc: str, path: tuple[str, ...]) -> None:
    """The inverse of the test above, and the half that was missing.

    `test_invocation_exists_in_the_cli` proves that every flag the docs *write*
    is real. It cannot notice a flag nobody wrote — so `docir build --title`
    went undocumented in both the guide and the README from the day it shipped,
    while `--logo`, added much later, was documented immediately. The reader's
    only signal was a site that called itself "Documentation".
    """
    text = GUIDE if doc == "guide" else _README
    missing = sorted(flag for flag in TREE[path] - _GLOBAL_FLAGS if flag not in text)
    assert not missing, (
        f"`docir {' '.join(path)}` has {', '.join(missing)}, "
        f"undocumented in the {doc} — a build that needs them looks like one that did not"
    )


# --- the repo's own prose: CLAUDE.md and the project store -------------------

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
_DELIBERATELY_UNREAL: dict[tuple[str, ...], str] = {
    ("upgrade",): "adr-31aa7aa60d11 rejects the bare verb; it shipped as `self upgrade`",
    ("serve",): "adr-a343140d72e2 weighs and rejects a live browser UI",
    ("schema", "accept"): "adr-bd3a820cc57a rejects an acknowledge-the-drift verb",
    ("schema", "add-type"): "adr-c0ce6f347f3e rejects writing the schema through the CLI",
    ("schema", "diff"): "issue-3678c897295f proposes it; still open",
    ("import",): "the bulk import repeatedly proposed and repeatedly rejected",
    ("repair",): "the name of the gap `check --fix` closed, quoted in the issues that closed it",
    ("accept-schema",): "run-f4a756206fe0 records that this verb deliberately does not exist",
    ("reindex", "--all"): "the flag that never existed — the defect issue-87a27629f6a6 is about",
}


def _exemption(invocation: str) -> tuple[str, ...] | None:
    """The exemption covering ``invocation``, if any."""
    tokens = tuple(_peel_globals(_tokens(invocation)[1:]))
    return next(
        (key for key in _DELIBERATELY_UNREAL if tokens[: len(key)] == key),
        None,
    )


def _repo_prose() -> dict[str, str]:
    """CLAUDE.md plus every markdown file in the project store, by name."""
    assert _STORE_DOCS.is_dir(), (
        f"{_STORE_DOCS} is missing — the suite runs from the checkout "
        "(test_installation.py pins that), so an absent store means this guard "
        "is scanning nothing rather than finding nothing"
    )
    sources = {"CLAUDE.md": (_REPO / "CLAUDE.md").read_text(encoding="utf-8")}
    for path in sorted(_STORE_DOCS.rglob("*.md")):
        sources[path.name] = path.read_text(encoding="utf-8")
    return sources


REPO_PROSE = _repo_prose()
REPO_INVOCATIONS = [
    (name, invocation) for name, text in REPO_PROSE.items() for invocation in _invocations(text)
]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("CLAUDE.md", "docir query --type decision"),
        ("CLAUDE.md", "docir get arch-1cfb1b212237"),
        ("CLAUDE.md", "docir add --type decision"),
        # The store: a fenced block, a table cell, and an inline span each.
        ("arch-1cfb1b212237", "docir check"),
        ("arch-1cfb1b212237", "docir reindex"),
        ("run-", "docir build --out"),
    ],
)
def test_the_corpus_extractor_finds_known_invocations(source: str, expected: str) -> None:
    """Guard the guard, again — over many files this matters more, not less.

    A path typo or a store that moved would leave the sweep below scanning an
    empty set and reporting success. Each entry here comes from a different
    file and a different markdown construct.
    """
    assert any(
        name.startswith(source) and invocation.startswith(expected)
        for name, invocation in REPO_INVOCATIONS
    ), f"extractor no longer finds {expected!r} in {source} — it is silently under-checking"


def test_the_corpus_sweep_covers_the_whole_store() -> None:
    """Every store document is read, not just the ones that happen to parse."""
    on_disk = {path.name for path in _STORE_DOCS.rglob("*.md")}
    assert on_disk <= set(REPO_PROSE), sorted(on_disk - set(REPO_PROSE))
    assert len(on_disk) > 100, f"only {len(on_disk)} store documents found — is the path right?"


@pytest.mark.parametrize(
    ("source", "invocation"),
    REPO_INVOCATIONS,
    ids=lambda value: value[:60] if isinstance(value, str) else value,
)
def test_repo_prose_invocation_exists_in_the_cli(source: str, invocation: str) -> None:
    """The same oracle, applied to what an agent working *in this repo* reads.

    CLAUDE.md tells an agent to read the store before changing anything, so a
    wrong command there is executed with the same confidence as a right one —
    the failure mode issue-87a27629f6a6 describes for the packaged guide, one
    repository closer.
    """
    problems = _problems(invocation)
    if not problems:
        return
    exemption = _exemption(invocation)
    assert exemption, f"{source}: " + "\n".join(problems)


@pytest.mark.parametrize("key", sorted(_DELIBERATELY_UNREAL), ids=lambda k: " ".join(k))
def test_every_exemption_is_still_needed(key: tuple[str, ...]) -> None:
    """An exemption outlives its prose, and then it hides the real thing.

    If `docir import` ever ships, its entry here would silently swallow a typo
    in every future invocation of it. Dropping the entry is part of shipping the
    command; this is what says so.
    """
    used = any(_exemption(invocation) == key for _, invocation in REPO_INVOCATIONS)
    assert used, (
        f"no prose still writes `docir {' '.join(key)}` — drop the exemption "
        f"({_DELIBERATELY_UNREAL[key]})"
    )


#: Names the binary has answered to before. A retired one is worse than a typo:
#: `docs check --strict` is a plausible-looking line that resolves to nothing on
#: any machine, and it survives every check above because the extractor is
#: anchored on `docir `. The architecture document carried 96 of them.
_RETIRED_BINARIES = frozenset({"docs"})

_RETIRED_INVOCATION = re.compile(rf"`({'|'.join(sorted(_RETIRED_BINARIES))}) ([a-z][a-z-]*)")


def _retired_binary_hits(text: str) -> list[str]:
    """Spans invoking a former binary name with a word that is a real command.

    Requiring the second word to be a live subcommand is what keeps `docs/` and
    `docs-schema.yaml` out (no space) and English plurals too: "the docs query
    the index" is prose, and prose is not in backticks.
    """
    return [
        f"{binary} {word}" for binary, word in _RETIRED_INVOCATION.findall(text) if (word,) in TREE
    ]


@pytest.mark.parametrize("source", sorted(REPO_PROSE))
def test_no_prose_invokes_a_retired_binary_name(source: str) -> None:
    hits = _retired_binary_hits(REPO_PROSE[source])
    assert not hits, (
        f"{source} invokes `{hits[0]}` — the binary is `docir`. "
        f"{len(hits)} occurrence(s); none of them run."
    )


@pytest.mark.parametrize("doc", ["guide", "readme"])
def test_no_shipped_doc_invokes_a_retired_binary_name(doc: str) -> None:
    text = GUIDE if doc == "guide" else _README
    hits = _retired_binary_hits(text)
    assert not hits, f"the {doc} invokes `{hits[0]}` — the binary is `docir`"


# --- the fifth source: docstrings under src/ --------------------------------

#: Source docstrings name commands constantly — `"""Create a new document
#: (``docir add``)."""` — and they rot exactly like prose does. The rename that
#: left 96 stale invocations in the architecture document left 37 more here,
#: where no docs check reaches: they are reStructuredText literals, not markdown
#: code spans, so the markdown extractor never sees them.
_SOURCE_ROOT = _REPO / "src" / "docir"

#: A command literal in a docstring: ``docir add`` or `docir add`.
_RST_LITERAL = re.compile(r"``?(docir [^`]+?)``?(?=[^`]|$)")


def _source_prose() -> dict[str, str]:
    """Every Python module under `src/`, by repo-relative path."""
    files = {
        str(path.relative_to(_REPO)): path.read_text(encoding="utf-8")
        for path in sorted(_SOURCE_ROOT.rglob("*.py"))
        # Alembic revisions are generated and excluded from every other gate.
        if "alembic" not in path.parts
    }
    assert len(files) > 50, f"only {len(files)} modules found — is {_SOURCE_ROOT} right?"
    return files


SOURCE_PROSE = _source_prose()

#: The same `_split` the markdown side uses, so a `$(...)` substitution and a
#: `|` alternative mean the same thing in a docstring as in a document. Docs
#: and docstrings quote the same shell lines — `app.py`'s help text carries the
#: `git diff --name-only ... | tr` pipeline the guide does — and two extractors
#: would eventually disagree about one of them.
SOURCE_INVOCATIONS = [
    (name, part)
    for name, text in SOURCE_PROSE.items()
    for match in _RST_LITERAL.findall(text)
    for part in _split(" ".join(match.split()))
]


def test_the_source_extractor_finds_known_invocations() -> None:
    """Guard the guard. 700 modules yielding nothing would pass silently."""
    found = {invocation for _, invocation in SOURCE_INVOCATIONS}
    for expected in ("docir add", "docir check --fix", "docir tag rename"):
        assert any(inv.startswith(expected) for inv in found), (
            f"extractor no longer finds {expected!r} in src/ — it is under-checking"
        )


@pytest.mark.parametrize(
    ("source", "invocation"),
    SOURCE_INVOCATIONS,
    ids=lambda value: value[:60] if isinstance(value, str) else value,
)
def test_source_docstring_invocation_exists_in_the_cli(source: str, invocation: str) -> None:
    problems = _problems(invocation)
    if not problems:
        return
    assert _exemption(invocation), f"{source}: " + "\n".join(problems)


@pytest.mark.parametrize("source", sorted(SOURCE_PROSE))
def test_no_source_docstring_invokes_a_retired_binary_name(source: str) -> None:
    """The check that would have caught all 37, and the reason it is separate.

    A literal opening with the old name never reaches the extractor above —
    it is anchored on `docir `, so the line reads as "nothing to validate".
    That is the same blind spot the markdown side had, one directory over.
    """
    hits = _retired_binary_hits(SOURCE_PROSE[source])
    assert not hits, (
        f"{source} documents `{hits[0]}` — the binary is `docir`. {len(hits)} occurrence(s)."
    )
