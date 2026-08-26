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

from docir.modules.agents.domain.results import InstallAction, InstalledFile

_ENTRY_POINTS = Path(__file__).resolve().parents[2] / "src" / "docir" / "entry_points"

#: A dict literal is treated as serializing a type when it names at least this
#: many of the type's fields as string keys. Below it, an overlap is a
#: coincidence (`{"path": ..., "note": ...}` says nothing); at four it is the
#: shape of the type.
_MATCH_THRESHOLD = 4

DECLARED = frozenset(field.name for field in dataclasses.fields(InstalledFile))

#: Where the one serializer is allowed to live. Named rather than counted: a
#: scan that found *nothing* and a scan that found only the sanctioned site
#: produce the same count, and only one of them means the guard is working.
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


def test_installed_file_has_exactly_one_serializer() -> None:
    sites = _serializers_of(DECLARED)
    assert [site[0] for site in sites] == [SANCTIONED], (
        "InstalledFile is serialized in "
        f"{[f'{name}:{line}' for name, line, _ in sites]} — route both commands "
        "through the single helper instead; a field added to one of two "
        "serializers is how `self upgrade` stopped reporting a skill's reference files"
    )


def test_the_one_serializer_emits_every_declared_field() -> None:
    """A field the serializer never emits is one no caller can act on."""
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
