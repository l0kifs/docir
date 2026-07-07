"""Tests for the markdown document store and tags.yaml store."""

from __future__ import annotations

from datetime import date

import pytest

from docir.domain.entities.document import Document
from docir.domain.entities.tag import Tag
from docir.domain.errors import DocumentNotFoundError
from docir.infrastructure.filesystem.markdown_store import MarkdownDocumentFileStore
from docir.infrastructure.filesystem.tag_file_store import YamlTagFileStore


def _doc(**kw: object) -> Document:
    defaults: dict[str, object] = {
        "id": "adr-0001",
        "title": "Auth strategy",
        "description": "How auth works.",
        "type": "decision",
        "status": "proposed",
        "created": date(2026, 1, 1),
        "updated": date(2026, 1, 2),
        "tags": ("auth",),
        "related": ("adr-0002",),
        "body": "# Heading\n\nSome body.",
    }
    defaults.update(kw)
    return Document(**defaults)  # type: ignore[arg-type]


class TestMarkdownStore:
    def test_write_read_round_trip(self, tmp_path) -> None:
        store = MarkdownDocumentFileStore(tmp_path)
        rel = store.write(_doc())
        assert rel == "decisions/adr-0001-auth-strategy.md"
        loaded = store.read(rel)
        assert loaded.id == "adr-0001"
        assert loaded.title == "Auth strategy"
        assert loaded.tags == ("auth",)
        assert loaded.related == ("adr-0002",)
        assert loaded.created == date(2026, 1, 1)
        assert "Some body" in loaded.body

    def test_archived_flag_persisted(self, tmp_path) -> None:
        store = MarkdownDocumentFileStore(tmp_path)
        rel = store.write(_doc(archived=True))
        assert store.read(rel).archived is True

    def test_path_is_stable_across_title_change(self, tmp_path) -> None:
        store = MarkdownDocumentFileStore(tmp_path)
        rel = store.write(_doc())
        # A later write reuses the stored path even if the title changed.
        rel2 = store.write(_doc(title="Renamed", path=rel))
        assert rel2 == rel
        assert store.read(rel).title == "Renamed"

    def test_read_missing_raises(self, tmp_path) -> None:
        store = MarkdownDocumentFileStore(tmp_path)
        with pytest.raises(DocumentNotFoundError):
            store.read("decisions/nope.md")

    def test_delete_is_safe_when_missing(self, tmp_path) -> None:
        store = MarkdownDocumentFileStore(tmp_path)
        store.delete("decisions/nope.md")  # no error

    def test_scan_yields_all(self, tmp_path) -> None:
        store = MarkdownDocumentFileStore(tmp_path)
        store.write(_doc())
        store.write(_doc(id="issue-0001", type="issue", related=(), tags=()))
        found = {d.id for d in store.scan()}
        assert found == {"adr-0001", "issue-0001"}

    def test_scan_empty_root(self, tmp_path) -> None:
        store = MarkdownDocumentFileStore(tmp_path / "missing")
        assert list(store.scan()) == []


class TestTagFileStore:
    def test_write_and_load(self, tmp_path) -> None:
        path = tmp_path / "tags.yaml"
        store = YamlTagFileStore(path)
        store.write([Tag("auth", "Auth."), Tag("api", "API.")])
        loaded = {t.key: t.description for t in store.load()}
        assert loaded == {"auth": "Auth.", "api": "API."}

    def test_load_missing_returns_empty(self, tmp_path) -> None:
        assert YamlTagFileStore(tmp_path / "none.yaml").load() == []

    def test_load_non_mapping_returns_empty(self, tmp_path) -> None:
        path = tmp_path / "tags.yaml"
        path.write_text("- a\n- b\n")
        assert YamlTagFileStore(path).load() == []
