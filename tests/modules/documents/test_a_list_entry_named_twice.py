"""A frontmatter list that names one entry twice (issue-413546da5db7).

A document's tags, code globs and edges are sets written in an order, but the
file could hold a repeat — a hand edit, a merge of two branches that each added
it, an MCP call — and the index could not. A repeated tag failed the tag index's
primary key on every `reindex`, after the file was already written. A repeated
glob or edge was dropped by the index and kept by the file, so the two hashed
differently and `--replace-body` refused the document as changed on disk,
forever: refetching re-read the same disagreement.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
import yaml

from docir.config.settings import Settings
from docir.entry_points.dispatch import Dispatcher
from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.value_objects.relations import RelatedRef


def _document(**lists: tuple[object, ...]) -> Document:
    day = date(2026, 9, 24)
    return Document(
        id="adr-0001",
        title="T",
        description="d",
        type="decision",
        status="proposed",
        created=day,
        updated=day,
        **lists,  # type: ignore[arg-type]
    )


def test_the_entity_keeps_each_entry_once_in_the_order_first_given() -> None:
    edge = RelatedRef("adr-0002")
    document = _document(
        tags=("y", "x", "y"),
        code=("b/**", "a/**", "b/**"),
        related=(edge, RelatedRef("adr-0003"), edge),
    )

    assert document.tags == ("y", "x")
    assert document.code == ("b/**", "a/**")
    assert document.related == (edge, RelatedRef("adr-0003"))


def test_two_kinds_to_one_target_are_not_a_repeat() -> None:
    # Which kind the author meant is a judgement, not a duplicate.
    edges = (RelatedRef("adr-0002"), RelatedRef("adr-0002", "refines"))

    assert _document(related=edges).related == edges


def _repeat_line(settings: Settings, doc_id: str, line: str) -> Path:
    (path,) = settings.docs_root.rglob(f"{doc_id}-*.md")
    text = path.read_text(encoding="utf-8")
    assert text.count(f"\n{line}\n") == 1, text
    path.write_text(text.replace(f"\n{line}\n", f"\n{line}\n{line}\n", 1), encoding="utf-8")
    return path


def _repeat_tag(seeded: Dispatcher, settings: Settings) -> tuple[str, str, Path]:
    return "adr-0001", "- auth", _repeat_line(settings, "adr-0001", "- auth")


def _repeat_glob(seeded: Dispatcher, settings: Settings) -> tuple[str, str, Path]:
    seeded.dispatch("update", {"doc_id": "adr-0001", "set_code": ["src/**"]})
    return "adr-0001", "- src/**", _repeat_line(settings, "adr-0001", "- src/**")


def _repeat_edge(seeded: Dispatcher, settings: Settings) -> tuple[str, str, Path]:
    return "issue-0001", "- adr-0001", _repeat_line(settings, "issue-0001", "- adr-0001")


Repeat = Callable[[Dispatcher, Settings], tuple[str, str, Path]]


@pytest.mark.parametrize("repeat", [_repeat_tag, _repeat_glob, _repeat_edge])
def test_a_hand_written_repeat_reindexes_takes_a_body_and_is_dropped_on_write(
    seeded: Dispatcher, settings: Settings, repeat: Repeat
) -> None:
    doc_id, line, path = repeat(seeded, settings)

    seeded.dispatch("reindex", {})
    seeded.dispatch("update", {"doc_id": doc_id, "replace_body": "Rewritten.", "force": True})

    assert path.read_text(encoding="utf-8").count(f"\n{line}\n") == 1


def test_a_repeat_sent_as_a_list_is_written_once(seeded: Dispatcher, settings: Settings) -> None:
    # The MCP tools pass their list through the dispatcher untouched, so a
    # repeat arrives here without any CLI parsing in front of it.
    view = seeded.dispatch(
        "add",
        {"type": "decision", "title": "Twice", "description": "d", "tags": ["auth", "auth"]},
    )

    (path,) = settings.docs_root.rglob(f"{view['id']}-*.md")
    assert path.read_text(encoding="utf-8").count("\n- auth\n") == 1
    seeded.dispatch("reindex", {})


def _repeated(findings: list[dict[str, object]]) -> list[dict[str, object]]:
    return [finding for finding in findings if finding["kind"] == "repeated-entry"]


def _updated(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])["updated"]


@pytest.mark.parametrize("repeat", [_repeat_tag, _repeat_glob, _repeat_edge])
def test_check_names_the_file_and_the_entry_it_repeats(
    seeded: Dispatcher, settings: Settings, repeat: Repeat
) -> None:
    # Only the file still shows a repeat — every read holds each entry once —
    # so this is the one place anybody learns the file says something else.
    doc_id, line, path = repeat(seeded, settings)

    (finding,) = _repeated(seeded.dispatch("check", {}))

    assert finding["doc_ids"] == (doc_id,)
    assert finding["severity"] == "warning"
    assert str(path.relative_to(settings.docs_root)) in str(finding["message"])
    assert line.removeprefix("- ") in str(finding["message"])


@pytest.mark.parametrize(
    ("second", "reported"),
    [("- to: adr-0001\n", True), ("- to: adr-0001\n  kind: refines\n", False)],
)
def test_an_edge_is_a_repeat_by_what_it_says_not_how_it_is_spelled(
    seeded: Dispatcher, settings: Settings, second: str, reported: bool
) -> None:
    (path,) = settings.docs_root.rglob("issue-0001-*.md")
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("\n- adr-0001\n", f"\n- adr-0001\n{second}", 1), "utf-8")

    assert bool(_repeated(seeded.dispatch("check", {}))) is reported


@pytest.mark.parametrize("repeat", [_repeat_tag, _repeat_glob, _repeat_edge])
def test_fix_drops_the_repeat_from_the_file_and_leaves_updated_alone(
    seeded: Dispatcher, settings: Settings, repeat: Repeat
) -> None:
    doc_id, line, path = repeat(seeded, settings)
    updated = _updated(path)

    result = seeded.dispatch("repair", {})

    (action,) = _repeated(result["actions"])
    assert action["doc_ids"] == (doc_id,)
    assert path.read_text(encoding="utf-8").count(f"\n{line}\n") == 1
    assert _updated(path) == updated
    assert not _repeated(result["remaining"])
    assert not _repeated(seeded.dispatch("repair", {})["actions"])
