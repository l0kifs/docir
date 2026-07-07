"""Integration tests for the tag-registry use cases."""

from __future__ import annotations

import pytest

from docir.application.dispatcher import Dispatcher
from docir.domain.errors import (
    TagAlreadyExistsError,
    TagInUseError,
    TagNotFoundError,
)
from docir.infrastructure.config.settings import Settings


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
