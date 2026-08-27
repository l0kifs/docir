#!/usr/bin/env python3
"""Every ``--expr`` and every ``docir ...`` in a markdown file must really work.

Written for release notes, which are the one surface docir's own guards do not
reach: the prose test covers what ships in the wheel and the repo's own files,
``lint --deep`` covers a store's documents, but a GitHub release body is written
once, published, and read by people who copy from it.

It takes a *file*, so it runs before publishing and needs no store, no index and
no network — which is also why this is a script rather than a test. Point it at
anything markdown.

Two classes of failure, both silent by nature.

An expression that compiles wrong:

* a bare ``null`` is a JMESPath *identifier*, not a literal, so ``owner ==
  null`` compares a key nothing carries against itself and returns the answer
  the author wanted for the wrong reason;
* a mistyped field evaluates to null, so the query matches nothing and reads
  exactly like a corpus with nothing wrong.

docir shipped both in v0.18.0's release notes.

And a command that does not exist. A release body announcing a feature is
exactly where a flag gets named from memory, and an agent will run a backticked
line regardless of the sentence around it — the failure issue-87a27629f6a6
records, which reached every adopting repository through the packaged guide.
That half is judged by :mod:`cli_oracle`, the same module the prose tests use,
so a line correct here cannot be wrong there.

Usage::

    uv run python scripts/check_expressions.py notes.md [more.md ...]
"""

from __future__ import annotations

import pathlib
import re
import sys

import cli_oracle

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


def check_expressions(path: pathlib.Path, text: str) -> list[str]:
    """Every ``--expr`` in one file that would not compile."""
    problems: list[str] = []
    for raw in _EXPR_ARG.findall(text):
        expression = _unescape_shell(raw)
        try:
            compile_expression(expression)
        except ValidationError as exc:
            problems.append(f"{path}: --expr {expression!r}\n    {exc}")
    return problems


def check_invocations(path: pathlib.Path, text: str) -> list[str]:
    """Every ``docir ...`` in one file that does not resolve to a real command.

    An exemption covers prose naming a verb *because it does not exist* — a
    release note may well say that the bulk import was rejected again. The
    retired binary name gets its own pass for the reason the prose tests give:
    a span opening with the old name never reaches the extractor at all, so it
    would read as nothing to validate.
    """
    problems = [
        f"{path}: {problem}"
        for invocation in cli_oracle.invocations(text)
        if cli_oracle.problems(invocation) and not cli_oracle.exemption(invocation)
        for problem in cli_oracle.problems(invocation)
    ]
    problems += [
        f"{path}: invokes `{hit}` — the binary is `docir`, so this line runs nowhere"
        for hit in cli_oracle.retired_binary_hits(text)
    ]
    return problems


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    expressions = invocations = 0
    problems: list[str] = []
    for name in argv:
        path = pathlib.Path(name)
        if not path.is_file():
            print(f"error: no file at {path}", file=sys.stderr)
            return 2
        text = path.read_text(encoding="utf-8")
        expressions += len(_EXPR_ARG.findall(text))
        invocations += len(cli_oracle.invocations(text))
        problems += check_expressions(path, text)
        problems += check_invocations(path, text)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    # Both counts are printed even when clean: "0 problems" and "nothing was
    # checked" are the one pair a gate must never conflate, and this gate has
    # two halves that go quiet independently — a release body full of commands
    # and no expression is the ordinary case.
    print(
        f"Checked {expressions} --expr argument(s) and {invocations} docir invocation(s) "
        f"in {len(argv)} file(s); {len(problems)} failing."
    )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
