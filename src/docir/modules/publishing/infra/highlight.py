"""Syntax colouring for published code blocks — five roles, no dependency.

A docs site whose code blocks are one flat grey makes the reader parse the
snippet before they can read it, and the snippets are the part a reader
actually copies: `docir build --out site/` says three different things
(command, subcommand, flag) in one line of undifferentiated text.

The whole vocabulary is five classes — comment, keyword, string,
function/command, flag — mapped to the ``--sy-*`` theme tokens. That ceiling
is deliberate. A general highlighter is a dependency (Pygments is ~4 MB and
would have to be inlined into every page for the site to stay
offline-complete) or a JS bundle fetched from a CDN, which a published site
must not do. Five roles over the languages a design corpus actually contains
is the whole benefit at none of that cost.

Two rules keep it honest rather than merely colourful:

* **Comments and strings are matched first**, in one alternation, so a ``#``
  inside a string is not a comment and a quote inside a comment does not open
  a string. Every other rule sees only what those two left behind.
* **An unknown language is not highlighted.** Guessing means colouring ``#``
  as a comment in a language where it is an operator — a wrong colour asserts
  a structure that is not there, which is worse than none. ``text`` and any
  unrecognised info string render plain.

Colouring runs on the *raw* source and escapes as it goes, because the
alternative — pattern-matching over already-rendered HTML — matches inside
entities and tag names the moment a snippet contains ``<``.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable

#: Info-string aliases per language family. The key is what the renderer
#: shows in the block's header; the value set is what a fence may say.
_ALIASES: dict[str, frozenset[str]] = {
    "shell": frozenset({"bash", "sh", "shell", "zsh", "console", "shell-session"}),
    "python": frozenset({"python", "py", "python3"}),
    "yaml": frozenset({"yaml", "yml"}),
    "json": frozenset({"json", "jsonc"}),
    "sql": frozenset({"sql", "postgresql", "sqlite"}),
    "toml": frozenset({"toml", "ini", "cfg"}),
}

_PY_KEYWORDS = frozenset({
    "and", "as", "assert", "async", "await", "break", "class", "continue", "def", "del",
    "elif", "else", "except", "finally", "for", "from", "global", "if", "import", "in",
    "is", "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try", "while",
    "with", "yield", "None", "True", "False", "self",
})  # fmt: skip

_SQL_KEYWORDS = frozenset({
    "select", "from", "where", "insert", "into", "values", "update", "set", "delete",
    "create", "table", "index", "view", "drop", "alter", "add", "column", "primary",
    "key", "foreign", "references", "on", "join", "left", "right", "inner", "outer",
    "group", "by", "order", "having", "limit", "offset", "distinct", "as", "and", "or",
    "not", "null", "is", "exists", "union", "all", "with", "returning", "conflict",
    "do", "nothing", "default", "constraint", "unique", "cascade",
})  # fmt: skip

_YAML_LITERALS = frozenset({"true", "false", "null", "yes", "no", "~"})

#: Shared string forms. Single-line only: a runaway quote must not swallow the
#: rest of the block, which is how a highlighter turns a typo into a blank page.
_STRING = r"\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'"

_SHELL_RE = re.compile(
    rf"(?P<cmt>\#[^\n]*)|(?P<str>{_STRING})"
    r"|(?P<flag>(?<![\w-])--?[A-Za-z][\w-]*)"
    r"|(?P<word>[A-Za-z_][\w.-]*)"
)

_PYTHON_RE = re.compile(
    r"(?P<cmt>\#[^\n]*)"
    r"|(?P<str>\"\"\"(?:[^\"\\]|\\.|\"(?!\"\"))*\"\"\""
    r"|'''(?:[^'\\]|\\.|'(?!''))*'''"
    rf"|{_STRING})"
    r"|(?P<dec>@[\w.]+)"
    r"|(?P<word>[A-Za-z_]\w*)"
)

_YAML_RE = re.compile(
    rf"(?P<cmt>\#[^\n]*)|(?P<str>{_STRING})"
    r"|(?P<key>^[ \t-]*[\w.-]+(?=\s*:))"
    r"|(?P<word>[A-Za-z_~][\w.-]*)",
    re.MULTILINE,
)

_JSON_RE = re.compile(
    r"(?P<key>\"(?:[^\"\\\n]|\\.)*\"(?=\s*:))"
    r"|(?P<str>\"(?:[^\"\\\n]|\\.)*\")"
    r"|(?P<num>-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"
    r"|(?P<word>true|false|null)"
)

_SQL_RE = re.compile(
    rf"(?P<cmt>--[^\n]*)|(?P<str>{_STRING})|(?P<word>[A-Za-z_]\w*)",
)

_TOML_RE = re.compile(
    rf"(?P<cmt>\#[^\n]*)|(?P<str>{_STRING})"
    r"|(?P<sect>^\s*\[+[^\]\n]+\]+)"
    r"|(?P<key>^\s*[\w.\"-]+(?=\s*=))"
    r"|(?P<word>true|false)",
    re.MULTILINE,
)


def language_label(info: str) -> str:
    """What the block's header shows: the fence's own word, or ``text``."""
    word = info.strip().split()[0].lower() if info.strip() else ""
    return word or "text"


def highlight(source: str, info: str) -> str:
    """Escaped HTML for a code block, with ``sy-*`` spans where recognised."""
    family = _family(language_label(info))
    if family is None:
        return html.escape(source)
    pattern, classify = family
    return _scan(source, pattern, classify)


#: One classifier *factory* per family, not one classifier: the shell and
#: python rules carry state across a block ("was the previous word `def`?"),
#: so a shared instance would leak one block's position into the next.
_Rule = tuple[re.Pattern[str], Callable[[re.Match[str]], str | None]]


def _family(label: str) -> _Rule | None:
    for name, aliases in _ALIASES.items():
        if label in aliases:
            return _FAMILIES[name]()
    return None


def _scan(
    source: str,
    pattern: re.Pattern[str],
    classify: Callable[[re.Match[str]], str | None],
) -> str:
    """Replace every match with a span, escaping the gaps between them.

    ``classify`` is called in document order and may carry state (the shell
    and python rules both need "what did the previous word mean?"), which is
    the reason for a fresh classifier per call rather than a module-level one.
    """
    out: list[str] = []
    position = 0
    for match in pattern.finditer(source):
        out.append(html.escape(source[position : match.start()]))
        css = classify(match)
        token = html.escape(match.group())
        out.append(f'<span class="{css}">{token}</span>' if css else token)
        position = match.end()
    out.append(html.escape(source[position:]))
    return "".join(out)


def _shell_classifier() -> Callable[[re.Match[str]], str | None]:
    """Command, subcommand, then plain — reset at every pipe or separator.

    A shell line's first bare word is what is being run and its second is
    almost always the subcommand (`docir get`, `git commit`, `uv run`); past
    that, words are arguments and colouring them says nothing. Keyword lists
    are the wrong model here — the interesting word in a docs snippet is the
    tool's own name, which no list can contain.
    """
    slot = 0
    end = 0

    def classify(match: re.Match[str]) -> str | None:
        nonlocal slot, end
        gap = match.string[end : match.start()]
        end = match.end()
        if re.search(r"[\n|;&()]|\$\(", gap):
            slot = 0
        kind = match.lastgroup
        if kind != "word":
            return f"sy-{kind}"
        slot += 1
        if slot == 1:
            return "sy-fn"
        return "sy-kw" if slot == 2 else None

    return classify


def _python_classifier() -> Callable[[re.Match[str]], str | None]:
    named = False

    def classify(match: re.Match[str]) -> str | None:
        nonlocal named
        kind = match.lastgroup
        if kind in {"cmt", "str"}:
            named = False
            return f"sy-{kind}"
        if kind == "dec":
            named = False
            return "sy-flag"
        word = match.group()
        if named:
            named = False
            return "sy-fn"
        named = word in {"def", "class"}
        return "sy-kw" if word in _PY_KEYWORDS else None

    return classify


def _yaml_classify(match: re.Match[str]) -> str | None:
    kind = match.lastgroup
    if kind in {"cmt", "str"}:
        return f"sy-{kind}"
    if kind == "key":
        return "sy-fn"
    return "sy-kw" if match.group().lower() in _YAML_LITERALS else None


def _json_classify(match: re.Match[str]) -> str | None:
    kind = match.lastgroup
    if kind == "key":
        return "sy-fn"
    if kind == "str":
        return "sy-str"
    return "sy-kw"


def _sql_classify(match: re.Match[str]) -> str | None:
    kind = match.lastgroup
    if kind in {"cmt", "str"}:
        return f"sy-{kind}"
    return "sy-kw" if match.group().lower() in _SQL_KEYWORDS else None


def _toml_classify(match: re.Match[str]) -> str | None:
    kind = match.lastgroup
    if kind in {"cmt", "str"}:
        return f"sy-{kind}"
    if kind == "sect":
        return "sy-flag"
    return "sy-fn" if kind == "key" else "sy-kw"


_FAMILIES: dict[str, Callable[[], _Rule]] = {
    "shell": lambda: (_SHELL_RE, _shell_classifier()),
    "python": lambda: (_PYTHON_RE, _python_classifier()),
    "yaml": lambda: (_YAML_RE, _yaml_classify),
    "json": lambda: (_JSON_RE, _json_classify),
    "sql": lambda: (_SQL_RE, _sql_classify),
    "toml": lambda: (_TOML_RE, _toml_classify),
}
