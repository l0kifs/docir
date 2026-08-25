#!/usr/bin/env python3
"""Every ``--expr`` argument in a markdown file must actually run.

Written for release notes, which are the one surface docir's own guards do not
reach: the prose test covers what ships in the wheel and ``lint --deep`` covers
a store's documents, but a GitHub release body is written once, published, and
read by people who copy from it.

It takes a *file*, so it runs before publishing and needs no network — which is
also why this is a script rather than a test. Point it at anything markdown.

Two failures it exists for, both silent by nature:

* a bare ``null`` is a JMESPath *identifier*, not a literal, so ``owner ==
  null`` compares a key nothing carries against itself and returns the answer
  the author wanted for the wrong reason;
* a mistyped field evaluates to null, so the query matches nothing and reads
  exactly like a corpus with nothing wrong.

docir shipped both in v0.18.0's release notes.

Usage::

    uv run python scripts/check_expressions.py notes.md [more.md ...]
"""

from __future__ import annotations

import pathlib
import re
import sys

from docir.modules.documents.domain.services.expressions import compile_expression
from docir.platform.errors import ValidationError

#: An explicit ``--expr`` followed by a quoted argument. Deliberately narrow:
#: a wider net over expression-shaped text matches quoted assertions, error
#: messages and prose comparisons far more often than real expressions.
_EXPR_ARG = re.compile(r'--expr\s+"([^"]+)"')


def _unescape_shell(expression: str) -> str:
    """The expression as docir receives it, not as bash carries it.

    A JMESPath literal is backtick-quoted, and a backtick inside double quotes
    is command substitution — so a *correct* shell example escapes them.
    Checking the prose verbatim would fail on documentation that is right.
    """
    return expression.replace("\\`", "`")


def check(path: pathlib.Path) -> list[str]:
    """Every failure in one file, as readable lines."""
    problems: list[str] = []
    for raw in _EXPR_ARG.findall(path.read_text(encoding="utf-8")):
        expression = _unescape_shell(raw)
        try:
            compile_expression(expression)
        except ValidationError as exc:
            problems.append(f"{path}: --expr {expression!r}\n    {exc}")
    return problems


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    checked, problems = 0, []
    for name in argv:
        path = pathlib.Path(name)
        if not path.is_file():
            print(f"error: no file at {path}", file=sys.stderr)
            return 2
        found = _EXPR_ARG.findall(path.read_text(encoding="utf-8"))
        checked += len(found)
        problems += check(path)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    # The count is printed even when clean: "0 problems" and "nothing was
    # checked" are the one pair a gate must never conflate.
    print(f"Checked {checked} --expr argument(s) in {len(argv)} file(s); {len(problems)} failing.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
