"""Integration tests for the tag-registry use cases."""

from __future__ import annotations

import pytest

from docir.config.settings import Settings
from docir.entry_points.dispatch import Dispatcher
from docir.platform.errors import (
    TagAlreadyExistsError,
    TagInUseError,
    TagNotFoundError,
)


def test_add_and_list(dispatcher: Dispatcher, settings: Settings) -> None:
    dispatcher.dispatch("tag_add", {"key": "auth", "description": "Auth."})
    dispatcher.dispatch("tag_add", {"key": "api", "description": "API."})
    tags = dispatcher.dispatch("tag_list", {})
    assert {t["key"] for t in tags} == {"auth", "api"}
    assert settings.tags_path.exists()


def test_add_duplicate_rejected(dispatcher: Dispatcher) -> None:
    dispatcher.dispatch("tag_add", {"key": "auth", "description": "Auth."})
    with pytest.raises(TagAlreadyExistsError):
        dispatcher.dispatch("tag_add", {"key": "auth", "description": "again"})


def test_rename_rewrites_documents(seeded: Dispatcher) -> None:
    seeded.dispatch("tag_rename", {"old": "auth", "new": "authn"})
    doc = seeded.dispatch("get", {"doc_id": "adr-0001"})
    assert "authn" in doc["tags"] and "auth" not in doc["tags"]
    keys = {t["key"] for t in seeded.dispatch("tag_list", {})}
    assert "authn" in keys and "auth" not in keys


def test_rename_missing_rejected(dispatcher: Dispatcher) -> None:
    with pytest.raises(TagNotFoundError):
        dispatcher.dispatch("tag_rename", {"old": "ghost", "new": "x"})


def test_rename_to_existing_rejected(seeded: Dispatcher) -> None:
    with pytest.raises(TagAlreadyExistsError):
        seeded.dispatch("tag_rename", {"old": "auth", "new": "api"})


def test_remove_in_use_blocked(seeded: Dispatcher) -> None:
    with pytest.raises(TagInUseError):
        seeded.dispatch("tag_remove", {"key": "auth"})


def test_remove_force_strips_from_documents(seeded: Dispatcher) -> None:
    seeded.dispatch("tag_remove", {"key": "auth", "force": True})
    doc = seeded.dispatch("get", {"doc_id": "adr-0001"})
    assert "auth" not in doc["tags"]
    assert all(t["key"] != "auth" for t in seeded.dispatch("tag_list", {}))


def test_remove_missing_rejected(dispatcher: Dispatcher) -> None:
    with pytest.raises(TagNotFoundError):
        dispatcher.dispatch("tag_remove", {"key": "ghost"})


def test_remove_unused_tag(dispatcher: Dispatcher) -> None:
    dispatcher.dispatch("tag_add", {"key": "lonely", "description": "x"})
    dispatcher.dispatch("tag_remove", {"key": "lonely"})
    assert dispatcher.dispatch("tag_list", {}) == []


# -- the staleness clock (GAP-020) ------------------------------------------
#
# `stale_reference_date()` falls back to `updated` when a document has no
# explicit `verified`, and tag rename/rm rewrote every referencing document with
# `updated = today`. A pure classification edit therefore made overdue documents
# report as freshly reviewed — a bulk administrative action silently forging the
# one trust signal the product offers, which is what ADR-0006 argues staleness
# must never be. `check --fix` and `delete --force` already leave `updated`
# alone for the same reason.


def _overdue_decision(settings: Settings, tag: str) -> None:
    """A decision far past its 365-day cadence, carrying ``tag``."""
    decisions = settings.docs_root / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    (decisions / "adr-0001-old.md").write_text(
        "---\n"
        "created: '2024-01-01'\n"
        "description: an old decision\n"
        "id: adr-0001\n"
        "related: []\n"
        "status: accepted\n"
        f"tags: [{tag}]\n"
        "title: Old decision\n"
        "type: decision\n"
        "updated: '2024-01-01'\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )


def test_rename_does_not_reset_the_staleness_clock(
    dispatcher: Dispatcher, settings: Settings
) -> None:
    dispatcher.dispatch("tag_add", {"key": "auth", "description": "Auth."})
    _overdue_decision(settings, "auth")
    dispatcher.dispatch("reindex", {})
    assert dispatcher.dispatch("get", {"doc_id": "adr-0001"})["stale"] is True

    dispatcher.dispatch("tag_rename", {"old": "auth", "new": "authn"})

    view = dispatcher.dispatch("get", {"doc_id": "adr-0001"})
    assert list(view["tags"]) == ["authn"]  # the rename did happen
    assert view["updated"] == "2024-01-01"  # ...without touching the clock
    assert view["stale"] is True


def test_force_remove_does_not_reset_the_staleness_clock(
    dispatcher: Dispatcher, settings: Settings
) -> None:
    dispatcher.dispatch("tag_add", {"key": "auth", "description": "Auth."})
    _overdue_decision(settings, "auth")
    dispatcher.dispatch("reindex", {})

    dispatcher.dispatch("tag_remove", {"key": "auth", "force": True})

    view = dispatcher.dispatch("get", {"doc_id": "adr-0001"})
    assert list(view["tags"]) == []
    assert view["updated"] == "2024-01-01"
    assert view["stale"] is True
