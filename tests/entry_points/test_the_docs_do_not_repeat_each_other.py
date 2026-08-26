"""The same fact in `README.md`, `CLAUDE.md` and the shipped guide, measured.

adr-7d9fbbf976e8 requires a feature to land on three surfaces — the packaged
skill (an agent in an adopter's repo), the CLI docstring, and `README.md` (a
human deciding whether to adopt). So *some* overlap is the design working: a
README that said "see the packaged skill" is useless to someone reading GitHub,
and it cannot link into a file that ships in the wheel.

What is not the design working is a 22-word sentence copy-pasted between them.
Those drift — the three surfaces are edited on different days for different
reasons — and when they do, nothing says which half is current.

There is no clean line between the two, and inventing one would either fail on
every correct restatement or excuse everything. So this is a **ratchet**, the
shape `tach.toml` already uses for the `platform -> *.domain` edges
(adr-d3e3616400bf): the overlap that exists today is recorded, reported, and
allowed only to shrink. A new repeat fails; removing one fails until the entry
goes too, which is what keeps the record true.

Repeats *within* the packaged guide are not here — they have their own test and
are not tolerated at all, because those seven files ship together and are read
by the same reader in the same session.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from docir.modules.agents.infra.template_provider import PackagedTemplateProvider

_REPO = Path(__file__).resolve().parents[2]

#: Words per shingle — the same window the guide's own test measured its way to.
SHINGLE = 7

#: How much of a span identifies it. Long enough that two different repeats do
#: not collide, short enough that editing the tail of one does not read as a new
#: repeat needing a new entry.
KEY_WORDS = 8

#: The cross-surface overlap as it stands. **Allowed to shrink, never to grow.**
#: An entry is `(files, first words of the repeated span)`.
BASELINE: frozenset[tuple[tuple[str, ...], str]] = frozenset(
    {
        # Three facts `CLAUDE.md` states in full rather than deferring to README:
        # it is the file an agent has loaded before its first edit, and README is
        # not. Kept deliberately, not pending.
        (
            ("CLAUDE.md", "README.md"),
            "precedence highest first `--home` `docir home` a project-local",
        ),
        (("CLAUDE.md", "README.md"), "dependencies flow `entry points modules platform config`"),
        (("CLAUDE.md", "README.md"), "each module exposes exactly one public file `api"),
        (("CLAUDE.md", "guide/SKILL.md"), "a `supersedes` edge points from the new"),
        (("CLAUDE.md", "guide/SKILL.md"), "a repair has nothing to read with"),
        (("CLAUDE.md", "guide/SKILL.md"), "inside the task that moved the code"),
        (("CLAUDE.md", "guide/SKILL.md"), "links them not because they scored and"),
        (("CLAUDE.md", "guide/SKILL.md"), "not addressable as a section the document"),
        (("CLAUDE.md", "guide/SKILL.md"), "read the document against the code as it"),
        (
            ("CLAUDE.md", "guide/reference/maintenance.md"),
            "`duplicate-id` `dangling` `malformed` the corpus is broken plus",
        ),
        (("README.md", "guide/SKILL.md"), "`docir query --code src auth login py`"),
        (("README.md", "guide/SKILL.md"), "`similarity` is the raw cosine against your"),
        (("README.md", "guide/SKILL.md"), "an absent field means its default no"),
        (("README.md", "guide/SKILL.md"), "fails when the code contradicts the decision and"),
        (("README.md", "guide/SKILL.md"), "is the only address every `related` edge has"),
        (("README.md", "guide/SKILL.md"), "with two or more ids the reply"),
        (
            ("README.md", "guide/reference/maintenance.md"),
            "`id` never it is the primary key changing",
        ),
        (("README.md", "guide/reference/publishing.md"), "`docir build --out site ` renders the"),
        (("README.md", "guide/reference/publishing.md"), "cdn jsdelivr net npm mermaid 11 16 1"),
        (
            ("README.md", "guide/reference/retrieval.md"),
            "this store s retrieval against tasks whose answers",
        ),
        (("README.md", "guide/reference/schema.md"), "`disable types ` is how you give one"),
        (("README.md", "guide/reference/schema.md"), "it never changes the exit code the schema"),
        (("README.md", "guide/reference/schema.md"), "whether the file loads and what it costs"),
        (
            ("README.md", "guide/reference/troubleshooting.md"),
            "where docir does not own its environment a",
        ),
    }
)


def _sources() -> dict[str, str]:
    """One entry per *surface*, which is not one entry per file.

    `CLAUDE.md` and `.claude/rules/**` are joined: the split moved prose out of
    the root file without changing who reads it, so measuring them apart would
    have reported this repo's duplication as fixed on the day it moved. It would
    also flag the split itself — each rule file restates its own one-line summary
    in CLAUDE.md, which is the arrangement, not a repeat.
    """
    templates = PackagedTemplateProvider()
    sources = {f"guide/{name}": text for name, text in templates.template("skill").items()}
    sources["writing/SKILL.md"] = templates.template("writing")["SKILL.md"]
    sources["README.md"] = (_REPO / "README.md").read_text(encoding="utf-8")
    rules = sorted((_REPO / ".claude" / "rules").rglob("*.md"))
    assert len(rules) > 10, f"only {len(rules)} rule files found — is the path right?"
    sources["CLAUDE.md"] = "\n".join(
        [(_REPO / "CLAUDE.md").read_text(encoding="utf-8")]
        + [path.read_text(encoding="utf-8") for path in rules]
    )
    return sources


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9`\-]+", re.sub(r"```.*?```", " ", text, flags=re.S).lower())


def _cross_surface_spans() -> set[tuple[tuple[str, ...], str]]:
    """Maximal repeated spans that are not confined to the packaged guide."""
    files = {name: _words(text) for name, text in _sources().items()}
    owners: dict[str, set[str]] = defaultdict(set)
    for name, words in files.items():
        for i in range(len(words) - SHINGLE + 1):
            owners[" ".join(words[i : i + SHINGLE])].add(name)

    spans: set[tuple[tuple[str, ...], str]] = set()
    for words in files.values():
        covered: dict[int, frozenset[str]] = {}
        for i in range(len(words) - SHINGLE + 1):
            sharers = owners[" ".join(words[i : i + SHINGLE])]
            if len(sharers) > 1:
                for offset in range(SHINGLE):
                    covered[i + offset] = frozenset(sharers)
        start = None
        for i in range(len(words) + 1):
            if i in covered and start is None:
                start = i
            elif i not in covered and start is not None:
                names = tuple(sorted(covered[start]))
                # Repeats inside the guide belong to the guide's own test, which
                # does not tolerate them at all.
                if not all(name.startswith("guide/") for name in names):
                    spans.add((names, " ".join(words[start:i][:KEY_WORDS])))
                start = None
    return spans


def test_the_sweep_reads_all_three_surfaces() -> None:
    """A guard on the guard: a missing file would make every case below vacuous."""
    sources = _sources()
    assert {"README.md", "CLAUDE.md"} <= set(sources)
    assert sum(name.startswith("guide/") for name in sources) >= 6
    assert all(len(_words(text)) > SHINGLE for text in sources.values())


def test_no_new_repeat_between_the_docs_and_the_shipped_guide() -> None:
    added = sorted(_cross_surface_spans() - BASELINE)
    assert not added, "new cross-surface repeat — say it in one place and link:\n" + "\n".join(
        f"  {list(names)}\n     ...{span}..." for names, span in added
    )


def test_the_baseline_holds_no_repeat_that_is_gone() -> None:
    """A ratchet that is not tightened stops being one.

    Deleting the entry is the point: the number in this file is the record of
    how much duplication the docs carry, and a record nobody prunes drifts the
    same way the prose it measures does.
    """
    gone = sorted(BASELINE - _cross_surface_spans())
    assert not gone, "these repeats are fixed — delete them from BASELINE:\n" + "\n".join(
        f"  {list(names)}: {span}" for names, span in gone
    )
