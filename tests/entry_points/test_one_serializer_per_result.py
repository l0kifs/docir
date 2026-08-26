"""Guards the defect class the `extras` field hit: two serializers of one type.

`InstalledFile` was turned into JSON in two places under `entry_points` — a
`_setup_file` helper for `docir self upgrade` and an inline dict literal in
`_emit_setup` for `docir agent install/update`. Both were correct until the type
grew `extras`/`removed`; the field reached one of them, and `self upgrade`
reported an install without naming the reference files it had just written.

Nothing failed. The two commands describe the same event, so one describing it
differently is always a defect — but no test compared them, and the JSON an
agent reads is not something a human notices going quiet.

Two guards, because either alone passes while the bug is present:

- **Singular** — exactly one place builds the dict. A second one is where the
  divergence comes from, and it is cheap to see at the AST level.
- **Complete** — that one place emits every declared field. A single serializer
  that silently drops a new field is the same outage with fewer suspects.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from docir.modules.agents.domain.results import InstallAction, InstalledFile
from docir.modules.documents.api import ConformanceReport
from docir.modules.publishing.api import PublishResult
from docir.modules.release.api import ReleaseStatus

_ENTRY_POINTS = Path(__file__).resolve().parents[2] / "src" / "docir" / "entry_points"

#: A dict literal is treated as serializing a type when it names at least this
#: many of the type's fields as string keys. Below it, an overlap is a
#: coincidence (`{"path": ..., "note": ...}` says nothing); at four it is the
#: shape of the type.
_MATCH_THRESHOLD = 4


@dataclasses.dataclass(frozen=True)
class Guarded:
    """A result type `entry_points` turns into JSON by hand."""

    #: The dataclass whose shape the serializer is supposed to reproduce.
    type: type
    #: Where its one serializer is allowed to live. Named rather than counted: a
    #: scan that found *nothing* and a scan that found only the sanctioned site
    #: produce the same count, and only one of them means the guard is working.
    site: str
    #: Fields deliberately kept out of the payload, each with the reason. An
    #: exemption with no reason beside it is indistinguishable from an oversight.
    withheld: dict[str, str] = dataclasses.field(default_factory=dict)

    @property
    def declared(self) -> frozenset[str]:
        return frozenset(field.name for field in dataclasses.fields(self.type))

    @property
    def expected(self) -> frozenset[str]:
        return self.declared - set(self.withheld)


#: Every result type whose JSON shape is built by hand under `entry_points`.
#: Request types are deliberately absent: `AddDocumentRequest` and friends are
#: built twice on purpose, once from CLI flags and once from MCP arguments
#: (adr-354a4270ecd8), so their invariant is that the two *agree* — a different
#: test, and one this file does not make.
GUARDED = [
    Guarded(InstalledFile, site="cli/app.py"),
    Guarded(ReleaseStatus, site="cli/app.py"),
    Guarded(ConformanceReport, site="cli/app.py"),
    Guarded(
        PublishResult,
        site="cli/app.py",
        withheld={"files": "`pages` already carries the count; the list is every filename written"},
    ),
]

IDS = [guarded.type.__name__ for guarded in GUARDED]
DECLARED = frozenset(field.name for field in dataclasses.fields(InstalledFile))
SANCTIONED = "cli/app.py"


def _dict_literal_keys(root: Path) -> list[tuple[str, int, frozenset[str]]]:
    """Every dict literal under ``root``, as (relative path, line, string keys)."""
    found: list[tuple[str, int, frozenset[str]]] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = frozenset(
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            )
            if keys:
                found.append((path.relative_to(root).as_posix(), node.lineno, keys))
    return found


def _serializers_of(fields: frozenset[str]) -> list[tuple[str, int, frozenset[str]]]:
    return [
        site
        for site in _dict_literal_keys(_ENTRY_POINTS)
        if len(site[2] & fields) >= _MATCH_THRESHOLD
    ]


def test_the_scan_sees_real_dict_literals() -> None:
    """A guard on the guard: a parse that found nothing would pass every case below."""
    literals = _dict_literal_keys(_ENTRY_POINTS)
    assert len(literals) > 20, f"only {len(literals)} dict literals under entry_points"


@pytest.mark.parametrize("guarded", GUARDED, ids=IDS)
def test_the_result_type_has_exactly_one_serializer(guarded: Guarded) -> None:
    sites = _serializers_of(guarded.declared)
    assert [site[0] for site in sites] == [guarded.site], (
        f"{guarded.type.__name__} is serialized in "
        f"{[f'{name}:{line}' for name, line, _ in sites]} — route every caller "
        "through one helper instead; a field added to one of two serializers is "
        "how `self upgrade` stopped reporting a skill's reference files"
    )


@pytest.mark.parametrize("guarded", GUARDED, ids=IDS)
def test_the_serializer_names_every_field_it_should(guarded: Guarded) -> None:
    """The keys the one dict literal carries, against the fields it stands for.

    Weaker than calling it (`{"note": file.path}` would satisfy this), which is
    why `InstalledFile` is also checked by invocation below. It is what covers
    the serializers that print instead of returning.
    """
    (_, _, keys), *rest = _serializers_of(guarded.declared)
    assert not rest, "more than one serializer — the case above says which"
    missing = guarded.expected - keys
    assert not missing, (
        f"{guarded.type.__name__} declares {sorted(missing)} and the payload never "
        "names them; emit them, or add them to `withheld` with the reason"
    )


@pytest.mark.parametrize("guarded", GUARDED, ids=IDS)
def test_every_withheld_field_still_exists(guarded: Guarded) -> None:
    """An exemption for a field that was renamed away silently widens the check."""
    unknown = sorted(set(guarded.withheld) - guarded.declared)
    assert not unknown, f"{guarded.type.__name__} withholds fields it does not have: {unknown}"


def test_the_installed_file_serializer_emits_every_field_when_called() -> None:
    """The stronger form, where a helper returns the dict instead of printing it.

    Reads the real values through, so a key present but wired to the wrong
    attribute still has to survive the round trip.
    """
    from docir.entry_points.cli.app import _setup_file

    emitted = set(
        _setup_file(
            InstalledFile(
                target="claude",
                path="/x/SKILL.md",
                action=InstallAction.UPDATED,
                previous_version="0.1.0",
                new_version="0.2.0",
                note="a note",
                extras=("reference/schema.md",),
                removed=("reference/gone.md",),
            )
        )
    )
    assert emitted == DECLARED, f"not emitted: {sorted(DECLARED - emitted)}"
