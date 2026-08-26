"""The packaged guide is seven files now; this checks they do not restate each other.

Splitting one file into seven made duplication cheap to introduce and invisible
to review: a fact stated in `maintenance.md` and again in `troubleshooting.md`
reads fine in either diff. It is also expensive — the reader who follows both
links pays for it twice, and the two copies drift, at which point the guide
contradicts itself and nothing says which half is current.

Writing this test found one: "the index is derived and gitignored, so ..." was
being derived in both files. It now lives with the `no-index` finding that
explains it, and the operational half points there.

**What it cannot see:** paraphrase. `SKILL.md` said "always batch" four times in
four different sentences, and no exact-match sweep would have caught any of it.
This catches copy-paste and near-copy-paste between files, which is the failure
mode a split introduces; judgement is still what catches the rest.
"""

from __future__ import annotations

import re
from collections import defaultdict

from docir.modules.agents.infra.template_provider import PackagedTemplateProvider

#: Words per shingle. Measured on this corpus rather than picked: at 6 the sweep
#: flags correct repetitions of command idioms (``docir reindex`` then ``docir
#: check``) and ordinary English; at 10 it finds nothing at all on a corpus that
#: demonstrably held a duplicated sentence. 7 is where the two separate.
SHINGLE = 7

#: Spans allowed to appear in more than one file, each with the reason. Matched
#: as a substring of the repeated span, so a phrase here excuses the repeat it
#: names and not the sentence that grows around it. Every entry must still match
#: something (see the last test): an allowance that outlives the duplication it
#: excused is how a guard quietly stops guarding.
ALLOWED = [
    (
        "and the command that closes it",
        "one file's `Contents` line, quoted by the other's pointer at it",
    ),
    (
        "index the daemon the model the installation",
        "`maintenance.md`'s pointer naming what `troubleshooting.md` covers",
    ),
    (
        "before `--limit` so the limit counts",
        "one mechanic, correctly stated for `--stale` and again for `--expr`",
    ),
    (
        "a status the type doesn t declare",
        "two claims: what `--override` refuses, and what a hand-edit leaves behind",
    ),
]


def _words(text: str) -> list[str]:
    """Prose words, with fenced code removed — examples are meant to be alike."""
    return re.findall(r"[a-z0-9`\-]+", re.sub(r"```.*?```", " ", text, flags=re.S).lower())


def _repeated_spans() -> list[tuple[str, tuple[str, ...]]]:
    """Maximal spans that appear in more than one file, with the files sharing them.

    Shingles slide, so one repeated sentence surfaces as several overlapping
    windows. Marking the words each shared window covers and taking the maximal
    runs turns those back into the phrase a reader would recognise — which is
    what the allowlist has to be written against, and what a failure has to show.
    """
    files = {
        name: _words(text) for name, text in PackagedTemplateProvider().template("skill").items()
    }
    owners: dict[str, set[str]] = defaultdict(set)
    for name, words in files.items():
        for i in range(len(words) - SHINGLE + 1):
            owners[" ".join(words[i : i + SHINGLE])].add(name)

    spans: list[tuple[str, tuple[str, ...]]] = []
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
                spans.append((" ".join(words[start:i]), tuple(sorted(covered[start]))))
                start = None
    # One span per repeat: both sides of a repeat produce the same text.
    return sorted(set(spans))


def _excuse(span: str) -> str | None:
    return next((reason for phrase, reason in ALLOWED if phrase in span), None)


def test_the_sweep_has_something_to_sweep() -> None:
    """A guard on the guard: an empty corpus would satisfy every case below."""
    files = PackagedTemplateProvider().template("skill")
    assert len(files) > 1, "the guide is one file — this test is checking nothing"
    assert all(len(_words(text)) > SHINGLE for text in files.values()), "a file yielded no prose"


def test_a_planted_repeat_is_found() -> None:
    """The sweep has to be shown to fire, not just to pass.

    Every other case here asserts an absence, and an absence is what a broken
    extractor reports too.
    """
    stolen = " ".join(_words(PackagedTemplateProvider().template("skill")["SKILL.md"])[40:60])
    words = {"a.md": _words(f"filler words here {stolen} and more"), "b.md": _words(stolen)}
    owners: dict[str, set[str]] = defaultdict(set)
    for name, ws in words.items():
        for i in range(len(ws) - SHINGLE + 1):
            owners[" ".join(ws[i : i + SHINGLE])].add(name)
    assert any(len(names) > 1 for names in owners.values()), "the sweep cannot see a verbatim copy"


def test_no_file_of_the_guide_restates_another() -> None:
    unexcused = [(span, names) for span, names in _repeated_spans() if not _excuse(span)]
    assert not unexcused, "the guide repeats itself:\n" + "\n".join(
        f"  {list(names)}\n     ...{span}..." for span, names in unexcused
    )


def test_every_allowance_is_still_needed() -> None:
    """An entry nothing matches is an exemption that has outlived its duplication.

    Left in place it silently widens what the test above accepts — the same
    failure `_DELIBERATELY_UNREAL` guards against in the CLI-prose sweep.
    """
    spans = [span for span, _ in _repeated_spans()]
    stale = [phrase for phrase, _ in ALLOWED if not any(phrase in span for span in spans)]
    assert not stale, f"allowances matching nothing, delete them: {stale}"
