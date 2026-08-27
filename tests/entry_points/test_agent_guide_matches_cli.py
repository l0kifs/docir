"""Every `docir ...` command in docir's own prose must exist in the CLI.

Guards issue-87a27629f6a6. The guide (`modules/agents/infra/templates/skill/`) is the one
artifact `docir agent install` copies into *other* repositories, so a wrong
instruction there is distributed to every adopting project and is executed by an
agent that has no way to know better. It told agents to run `docir reindex
--all` — a flag that has never existed — at the single most important recovery
step ("after any merge/pull"). Nothing checked the guide against the CLI it
documents, so the error survived until a human happened to run the line.

The oracle is the CLI's own command tree, introspected rather than shelled out:
the same object `docir --help` prints from, so the test cannot drift from the
binary. A flag removed from `app.py` fails here in the same commit.

Every surface that names a command is checked, because the same rot reaches all
of them and only the first was covered. The guide and the README are what an
*adopter* reads; `CLAUDE.md`, the path-scoped rules beside it (`.claude/rules/**`)
and the project store (`.docir/docs/**`) are what an agent working *in this repo*
reads — CLAUDE.md points at the store first and keeps one line per invariant, with
the argument in a rule file that loads with the code it governs; docstrings under
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
from cli_oracle import (
    DELIBERATELY_UNREAL,
    TREE,
    exemption,
    invocations,
    problems,
    retired_binary_hits,
    split_line,
)

from docir.modules.agents.infra.template_provider import PackagedTemplateProvider
from docir.modules.documents.infra.profiles import PROFILE_NAMES
from docir.modules.documents.infra.schema_loader import parse_schema
from docir.platform import naming

_REPO = pathlib.Path(__file__).resolve().parents[2]

#: docir's own front door. It goes stale the same way the packaged guide
#: does and is the first thing an adopter reads.
_README = (_REPO / "README.md").read_text(encoding="utf-8")

#: The repo-local store. docir documents itself in docir, so these files are
#: the working instructions for anyone (human or agent) changing this codebase,
#: and CLAUDE.md sends readers to them before it explains anything itself.
_STORE_DOCS = _REPO / ".docir" / "docs"

#: The path-scoped rules CLAUDE.md was split into. Claude Code loads one when it
#: reads a file the rule's `paths:` matches, so this is the same prose CLAUDE.md
#: used to carry inline — three quarters of it — and it goes stale the same way.
#: Sweeping it is what stops the split from turning this guard into a count that
#: cannot tell "nothing is wrong" from "nothing is checked".
_RULES = _REPO / ".claude" / "rules"


_SKILL_TEMPLATE = PackagedTemplateProvider().template("skill")

#: The CLI guide as one text. It is a *directory* now — `SKILL.md` plus the
#: reference files it links — but every check below asks a question about the
#: guide, not about one of its files: "is `--title` documented" is answered by
#: whichever file documents it, and a command moved from the entry point into
#: `reference/` has not stopped being documented. Joining them keeps the whole
#: guide in scope, which is what stops the split from quietly shrinking what is
#: checked.
GUIDE = "\n".join(_SKILL_TEMPLATE[key] for key in sorted(_SKILL_TEMPLATE))
INVOCATIONS = invocations(GUIDE)


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
    assert not problems(invocation), "\n".join(problems(invocation))


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


def _repo_prose() -> dict[str, str]:
    """CLAUDE.md, the rules it was split into, and the project store, by name."""
    assert _STORE_DOCS.is_dir(), (
        f"{_STORE_DOCS} is missing — the suite runs from the checkout "
        "(test_installation.py pins that), so an absent store means this guard "
        "is scanning nothing rather than finding nothing"
    )
    assert _RULES.is_dir(), (
        f"{_RULES} is missing — CLAUDE.md keeps one line per invariant and sends "
        "the argument there, so an absent directory means this guard silently "
        "stopped reading most of what an agent in this repo is told"
    )
    sources = {"CLAUDE.md": (_REPO / "CLAUDE.md").read_text(encoding="utf-8")}
    for path in sorted(_RULES.rglob("*.md")):
        sources[f"rules/{path.name}"] = path.read_text(encoding="utf-8")
    for path in sorted(_STORE_DOCS.rglob("*.md")):
        sources[path.name] = path.read_text(encoding="utf-8")
    return sources


REPO_PROSE = _repo_prose()
REPO_INVOCATIONS = [
    (name, invocation) for name, text in REPO_PROSE.items() for invocation in invocations(text)
]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("CLAUDE.md", "docir query --type decision"),
        ("CLAUDE.md", "docir get arch-1cfb1b212237"),
        ("CLAUDE.md", "docir add --type decision"),
        # A rule file, which is where most of CLAUDE.md's prose now lives.
        ("rules/checks-and-lint.md", "docir check --fix"),
        # The store: a fenced block, a table cell, and an inline span each.
        # `docir check` anchors the CLI-surface document rather than the spine:
        # the architecture split moved the command vocabulary out of the latter,
        # and an anchor is only worth having where the content actually lives.
        ("arch-7fd54a82f7d6", "docir check"),
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


def test_the_rules_sweep_covers_every_rule_file() -> None:
    """The split moved prose out of CLAUDE.md; the sweep has to follow it.

    A rule file added later is covered by being written, not by anyone
    remembering this test — which is the property the store assertion below
    has, one directory over.
    """
    on_disk = {f"rules/{path.name}" for path in _RULES.rglob("*.md")}
    assert on_disk <= set(REPO_PROSE), sorted(on_disk - set(REPO_PROSE))
    assert len(on_disk) > 10, f"only {len(on_disk)} rule files found — is the path right?"


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
    found = problems(invocation)
    if not found:
        return
    assert exemption(invocation), f"{source}: " + "\n".join(found)


@pytest.mark.parametrize("key", sorted(DELIBERATELY_UNREAL), ids=lambda k: " ".join(k))
def test_every_exemption_is_still_needed(key: tuple[str, ...]) -> None:
    """An exemption outlives its prose, and then it hides the real thing.

    If `docir import` ever ships, its entry here would silently swallow a typo
    in every future invocation of it. Dropping the entry is part of shipping the
    command; this is what says so.
    """
    used = any(exemption(invocation) == key for _, invocation in REPO_INVOCATIONS)
    assert used, (
        f"no prose still writes `docir {' '.join(key)}` — drop the exemption "
        f"({DELIBERATELY_UNREAL[key]})"
    )


@pytest.mark.parametrize("source", sorted(REPO_PROSE))
def test_no_prose_invokes_a_retired_binary_name(source: str) -> None:
    hits = retired_binary_hits(REPO_PROSE[source])
    assert not hits, (
        f"{source} invokes `{hits[0]}` — the binary is `docir`. "
        f"{len(hits)} occurrence(s); none of them run."
    )


@pytest.mark.parametrize("doc", ["guide", "readme"])
def test_no_shipped_doc_invokes_a_retired_binary_name(doc: str) -> None:
    text = GUIDE if doc == "guide" else _README
    hits = retired_binary_hits(text)
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

#: The same `split_line` the markdown side uses, so a `$(...)` substitution and a
#: `|` alternative mean the same thing in a docstring as in a document. Docs
#: and docstrings quote the same shell lines — `app.py`'s help text carries the
#: `git diff --name-only ... | tr` pipeline the guide does — and two extractors
#: would eventually disagree about one of them.
SOURCE_INVOCATIONS = [
    (name, part)
    for name, text in SOURCE_PROSE.items()
    for match in _RST_LITERAL.findall(text)
    for part in split_line(" ".join(match.split()))
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
    found = problems(invocation)
    if not found:
        return
    assert exemption(invocation), f"{source}: " + "\n".join(found)


@pytest.mark.parametrize("source", sorted(SOURCE_PROSE))
def test_no_source_docstring_invokes_a_retired_binary_name(source: str) -> None:
    """The check that would have caught all 37, and the reason it is separate.

    A literal opening with the old name never reaches the extractor above —
    it is anchored on `docir `, so the line reads as "nothing to validate".
    That is the same blind spot the markdown side had, one directory over.
    """
    hits = retired_binary_hits(SOURCE_PROSE[source])
    assert not hits, (
        f"{source} documents `{hits[0]}` — the binary is `docir`. {len(hits)} occurrence(s)."
    )


# --- the sixth source: markdown shipped inside the package ------------------

#: The `CONTRACT.md` beside each module's `api.py`. §8.6 makes them change in
#: the same commit as the surface they document, so they are the one document
#: class guaranteed to be edited whenever a module's public operations move —
#: which is exactly when a command name in one goes stale. They ship in the
#: wheel, and until now nothing read them.
#:
#: The CLI guide's own files are deliberately excluded: they are already checked
#: through `PackagedTemplateProvider` above, and covering them twice would double
#: every one of their cases. The exclusion is by *identity* — every text the
#: `skill` template serves — not by directory, so a second template added beside
#: it (`writing/`) is picked up here, and so is a reference file that has somehow
#: stopped being served.
_GUIDE_TEXTS = frozenset(_SKILL_TEMPLATE.values())
_PACKAGED_MD = {
    str(path.relative_to(_REPO)): path.read_text(encoding="utf-8")
    for path in sorted((_REPO / "src").rglob("*.md"))
    if path.read_text(encoding="utf-8") not in _GUIDE_TEXTS
}

PACKAGED_INVOCATIONS = [
    (name, invocation) for name, text in _PACKAGED_MD.items() for invocation in invocations(text)
]


def test_every_module_contract_is_read() -> None:
    """One `CONTRACT.md` per module, and the sweep must see all of them.

    A module whose contract is missing from this set is either absent from the
    tree or excluded by accident; both look identical to "checked and clean".
    """
    modules = {
        path.name for path in (_REPO / "src" / "docir" / "modules").iterdir() if path.is_dir()
    }
    modules -= {"__pycache__"}
    read = {name.split("/")[-2] for name in _PACKAGED_MD if name.endswith("CONTRACT.md")}
    assert modules == read, f"contracts not read: {sorted(modules - read)}"


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        # One anchor per contract that names a command at all, so a file
        # dropping out of the sweep is visible rather than merely quieter.
        ("documents", "docir schema show"),
        ("publishing", "docir get"),
        ("release", "docir self upgrade"),
        ("tags", "docir check"),
    ],
)
def test_the_packaged_extractor_finds_known_invocations(module: str, expected: str) -> None:
    assert any(
        f"/{module}/" in name and invocation.startswith(expected)
        for name, invocation in PACKAGED_INVOCATIONS
    ), f"extractor no longer finds {expected!r} in {module}/CONTRACT.md — under-checking"


@pytest.mark.parametrize(
    ("source", "invocation"),
    PACKAGED_INVOCATIONS,
    ids=lambda value: value[:60] if isinstance(value, str) else value,
)
def test_packaged_markdown_invocation_exists_in_the_cli(source: str, invocation: str) -> None:
    found = problems(invocation)
    if not found:
        return
    assert exemption(invocation), f"{source}: " + "\n".join(found)


@pytest.mark.parametrize("source", sorted(_PACKAGED_MD))
def test_no_packaged_markdown_invokes_a_retired_binary_name(source: str) -> None:
    hits = retired_binary_hits(_PACKAGED_MD[source])
    assert not hits, f"{source} invokes `{hits[0]}` — the binary is `docir`"


# --- document ids: prose may not name one the corpus does not carry ---------
#
# The commands above are checked against the CLI; the *ids* were checked against
# nothing. Both halves of this file's premise apply to them equally — a
# `related` edge is validated at write time, but an id written into a docstring
# or the packaged skill is prose, and prose is where a fabricated one survives.
# Two were written in consecutive changes: an ADR cited before it was recorded,
# so it never resolved at all.
#
# Scope is the **package** prose only. The corpus's own unresolved mentions are
# already decided: adr-e86c5040d626 measured all 47 of them as documentation
# examples and deliberately made them a `lint --deep` advisory rather than a
# gate. This covers what ships in the wheel, where nothing looked before.

#: Ids that must not resolve, and why. Same contract as `DELIBERATELY_UNREAL`:
#: an entry that stops appearing is removed by the test below, so a stale
#: exemption cannot shadow a real fabrication.
_EXAMPLE_IDS: dict[str, str] = {
    # The random-id shape, in prose explaining what ids look like.
    "adr-3f9a2b1c7d4e": "the id the docs use to show the random format",
    "adr-0a1b2c3d4e5f": "a second one, in the bench fixture's shape",
    "tp-3f9a2b1c7d4e": "the same shape under the schema docs' example type `tp`",
    # The sequential shape. This store mints `random`, so a four-digit suffix
    # is visibly an example — which is exactly why the docstrings reach for it.
    "adr-0001": "sequential-style example",
    "adr-0007": "sequential-style example, the one most prose uses",
    "arch-0002": "sequential-style example, in a `--related` illustration",
    "issue-0003": "sequential-style example, in a `--related` illustration",
    "tp-0001": "sequential-style example under the schema docs' `tp` type",
    "tp-0007": "sequential-style example under the schema docs' `tp` type",
    # Not an example of an id at all: the pair that explains why the scanner is
    # restricted to known prefixes.
    "adr-1beef": "the foil in `adr-1beef` vs `sha-1beef`",
}


#: The id prefixes docir can mint, from the core plus every bundled profile —
#: the same reasoning `_shipped_vocabulary` uses. Restricting the scan to these
#: is what keeps `sha-1beef` in a sentence about hashing from reading as an id.
_KNOWN_PREFIXES = frozenset(
    schema.prefix for schema in parse_schema({"profiles": list(PROFILE_NAMES)}).types.values()
)


def _corpus_ids() -> frozenset[str]:
    """Every id the store actually carries, read from frontmatter.

    From the files rather than the index: this test runs in CI on a fresh
    clone, where the index is gitignored and does not exist yet.
    """
    found: set[str] = set()
    for path in (_REPO / ".docir" / "docs").rglob("*.md"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("id:"):
                found.add(line.split(":", 1)[1].strip())
                break
    return frozenset(found)


CORPUS_IDS = _corpus_ids()

#: Prose that ships in the wheel or governs the repo, keyed for a readable
#: failure. `REPO_PROSE` (README, CLAUDE.md, the corpus) is deliberately absent:
#: its corpus half is adr-e86c5040d626's, and its two files are covered here.
_ID_PROSE: dict[str, str] = {
    "skill/": GUIDE,
    "README.md": (_REPO / "README.md").read_text(encoding="utf-8"),
    "CLAUDE.md": (_REPO / "CLAUDE.md").read_text(encoding="utf-8"),
    **{
        f"rules/{path.name}": path.read_text(encoding="utf-8")
        for path in sorted(_RULES.rglob("*.md"))
    },
    **_PACKAGED_MD,
    **{f"docstring:{name}": text for name, text in SOURCE_PROSE.items()},
}

ID_MENTIONS = [
    (name, doc_id)
    for name, text in _ID_PROSE.items()
    for doc_id in sorted(set(naming.scan_document_ids(text, _KNOWN_PREFIXES)))
]


def test_the_corpus_has_ids_to_check_against() -> None:
    """A guard on the guard: an empty corpus would pass every case below."""
    assert len(CORPUS_IDS) > 50, f"only {len(CORPUS_IDS)} ids read — the sweep found nothing"


def test_the_id_extractor_finds_a_known_mention() -> None:
    assert any(doc_id == "adr-927aa43d9635" for _name, doc_id in ID_MENTIONS), (
        "extractor no longer finds a known ADR citation — under-checking"
    )


@pytest.mark.parametrize(
    ("source", "doc_id"), ID_MENTIONS, ids=lambda v: v if isinstance(v, str) else str(v)
)
def test_prose_names_no_document_the_corpus_lacks(source: str, doc_id: str) -> None:
    if doc_id in _EXAMPLE_IDS:
        return
    assert doc_id in CORPUS_IDS, (
        f"{source} names {doc_id!r}, which no document carries. Either the id is "
        f"fabricated, or it is an example and belongs in _EXAMPLE_IDS."
    )


@pytest.mark.parametrize("doc_id", sorted(_EXAMPLE_IDS))
def test_every_example_id_is_still_used(doc_id: str) -> None:
    """A stale exemption is a hole: it would silently excuse a real fabrication
    that happened to reuse the id."""
    assert any(found == doc_id for _name, found in ID_MENTIONS), (
        f"{doc_id!r} is exempted as an example and no longer appears — drop it "
        f"from _EXAMPLE_IDS ({_EXAMPLE_IDS[doc_id]})"
    )


def test_an_example_id_must_not_be_a_real_one(doc_id: str = "") -> None:
    """The exemption list may not quietly cover a document that exists."""
    overlap = sorted(set(_EXAMPLE_IDS) & CORPUS_IDS)
    assert not overlap, f"exempted as examples but real: {overlap}"


# --- `--expr` arguments in prose must compile ------------------------------
#
# The invocation tests above prove a documented command *resolves* — that its
# name and flags exist. They say nothing about the argument, and `--expr` is the
# one flag whose argument is a language. A wrong expression looks exactly like a
# right one until somebody runs it.
#
# Scoped to explicit `--expr "..."` occurrences rather than anything
# expression-shaped. A sweep of backticked spans across the corpus found 18
# candidates and 13 "failures", of which one was real: the rest were quoted
# assertions, error messages and prose comparisons (`old == new`). Text does not
# distinguish an expression from a sentence about one, and an invocation does.


def _unescape_shell(expression: str) -> str:
    """The expression as docir receives it, not as bash carries it.

    A JMESPath literal is backtick-quoted and a backtick inside double quotes is
    command substitution, so a correct shell example escapes them — `\\`0\\``.
    Compiling the prose verbatim would fail on documentation that is right.
    """
    return expression.replace("\\`", "`")


_EXPR_ARGS = [
    (name, _unescape_shell(expression))
    for name, text in {**_ID_PROSE, **REPO_PROSE}.items()
    for expression in re.findall(r'--expr\s+"([^"]+)"', text)
]


def test_the_expr_extractor_finds_a_known_example() -> None:
    assert any("related" in expression for _name, expression in _EXPR_ARGS), (
        "extractor no longer finds a documented --expr argument — under-checking"
    )


@pytest.mark.parametrize(
    ("source", "expression"), _EXPR_ARGS, ids=lambda v: v.replace(" ", "_")[:40]
)
def test_a_documented_expression_compiles(source: str, expression: str) -> None:
    """Two faults this catches, both of which shipped before it existed.

    A bare `null` is an *identifier* in JMESPath, not a literal, so
    `owner == null` compared a key no document carries against itself — the
    right answer for the wrong reason. And a bare `0` is not a literal at all.
    Every place docir documented `--expr` carried one or the other.
    """
    from docir.modules.documents.domain.services.expressions import compile_expression

    compile_expression(expression)
