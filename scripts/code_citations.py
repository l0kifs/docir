"""The oracle behind the check on `file.py:line` references in docir's prose.

A citation into the source is a promise that a reader following it lands on the
thing the sentence is about. Line numbers do not keep that promise: every
insertion above one moves it, silently, and the string that results is
indistinguishable from a correct one. Reading the corpus against its code turned
up five documents whose citation columns had shifted *wholesale* — an
architecture note on the **write** path pointing `IndexProjected` into
`_ranking_trace`, a read-path helper; a tag note pointing `TagRenamed` at the
`TagService` class header while `rename` sat eighty lines below
(issue-d4b194eca41d).

Two things are checkable and one is not, and the split is the whole design.

**Checkable:** the file resolves, and the line exists in it. That catches a
citation into a file that was split or shrank — twelve of this store's, all into
a `graph_checks.py` whose checks moved under `checks/`.

**Not checkable:** whether an in-bounds line is the *right* line. Nothing in the
text says what the author meant, so a sampled eighteen had to be read by
hand; seven pointed at the wrong symbol. That is the failure this module exists
to stop recurring, and it cannot be stopped by looking harder at a bare number.

**So a new citation has to carry its own redundancy**: the symbol it points at,
named beside it, which :func:`checked_pairs` verifies actually spans the line.

    `document_service.py:250` (`DocumentService.update`)

Now the two halves can disagree, and disagreement is detectable in the commit
that causes it. Existing citations are grandfathered by a baseline that may only
shrink — the ratchet `test_the_docs_do_not_repeat_each_other` already uses, for
the same reason: a rule worth keeping is worth adopting without a flag day.
"""

from __future__ import annotations

import ast
import pathlib
import re

#: A citation: a `.py` path or bare filename, a line, optionally a range.
CITATION = re.compile(r"([A-Za-z_0-9/.-]*[A-Za-z_0-9]+\.py):(\d+)(?:-(\d+))?")

#: The symbol a citation may name, immediately after it: ``(`Thing.method`)`` or
#: the literal ``(module level)`` for a constant or an import block.
PAIRED = re.compile(r"\A[`\s]*\(\s*(?:`([A-Za-z_][A-Za-z_0-9.]*)`|(module level))\s*\)")

_ROOTS = ("src", "scripts", "tests", "benchmarks")


def _by_name(repo: pathlib.Path) -> dict[str, list[pathlib.Path]]:
    found: dict[str, list[pathlib.Path]] = {}
    for root in _ROOTS:
        for path in (repo / root).rglob("*.py"):
            found.setdefault(path.name, []).append(path)
    return found


def resolve(repo: pathlib.Path, reference: str) -> pathlib.Path | None:
    """The file a citation names, or ``None`` when it names no single file.

    A repo-relative path wins outright. A bare filename resolves only when it is
    unique — ``dto.py`` exists under both `tags` and `documents`, and guessing
    between them is how a checker reports a healthy citation as broken, which
    is worse than declining to judge it.
    """
    direct = repo / reference
    if direct.is_file():
        return direct
    candidates = _by_name(repo).get(pathlib.PurePath(reference).name, [])
    return candidates[0] if len(candidates) == 1 else None


def symbol_at(path: pathlib.Path, line: int) -> str | None:
    """The innermost class or function spanning ``line``, or ``None``.

    Innermost, because a method inside a class should read as the method: the
    enclosing class is true and useless. ``None`` means module level — a
    constant, an import, a docstring — which is a real place for a citation to
    point and is spelled ``(module level)`` in the paired form.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    spans = [
        (node.lineno, node.end_lineno or node.lineno, node.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.lineno <= line <= (node.end_lineno or node.lineno)
    ]
    return sorted(spans)[-1][2] if spans else None


def citations(text: str) -> list[tuple[str, int, str | None]]:
    """Every citation in ``text`` as ``(reference, line, named symbol or None)``.

    The symbol is what the prose claims, not what the file holds; comparing the
    two is :func:`problems`' job.
    """
    found = []
    for match in CITATION.finditer(text):
        paired = PAIRED.match(text[match.end() : match.end() + 60])
        named = None
        if paired:
            named = paired.group(1) or "(module level)"
        found.append((match.group(1), int(match.group(2)), named))
    return found


def problems(repo: pathlib.Path, text: str, *, require_pair: bool) -> list[str]:
    """What is wrong with the citations in ``text``.

    ``require_pair`` is off for the grandfathered set and on for everything
    else, which is what lets the rule arrive without a flag day.
    """
    issues = []
    for reference, line, named in citations(text):
        path = resolve(repo, reference)
        if path is None:
            issues.append(f"{reference}:{line} — names no single file under {'/, '.join(_ROOTS)}/")
            continue
        total = len(path.read_text(encoding="utf-8").splitlines())
        if line > total:
            issues.append(f"{reference}:{line} — past end of file ({total} lines)")
            continue
        actual = symbol_at(path, line) or "(module level)"
        if named is None:
            if require_pair:
                issues.append(
                    f"{reference}:{line} — a line citation must name what it points at: "
                    f"write ``{reference}:{line}`` (`{actual}`)"
                )
            continue
        if named.split(".")[-1] != actual.split(".")[-1]:
            issues.append(f"{reference}:{line} — names `{named}`, but line {line} is in `{actual}`")
    return issues
