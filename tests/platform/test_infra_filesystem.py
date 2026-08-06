"""Tests for the markdown document store and tags.yaml store."""

from __future__ import annotations

from datetime import date

import pytest

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.value_objects.relations import RelatedRef
from docir.modules.tags.domain.entities.tag import Tag
from docir.platform.errors import DocumentNotFoundError, ValidationError
from docir.platform.filesystem.markdown_store import MarkdownDocumentFileStore
from docir.platform.filesystem.tag_store import YamlTagFileStore

# A file whose YAML is valid but whose `created`/`updated` is not an ISO date —
# the shape a hand-edit or a foreign file produces.
_MALFORMED = (
    "---\nid: adr-9999\ntitle: Broken\ndescription: d\ntype: decision\n"
    "status: proposed\ncreated: not-a-date\nupdated: not-a-date\n"
    "tags: []\nrelated: []\n---\n\nbody\n"
)


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
        "related": (RelatedRef("adr-0002"),),
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
        assert loaded.related == (RelatedRef("adr-0002"),)
        assert loaded.created == date(2026, 1, 1)
        assert "Some body" in loaded.body

    def test_typed_edges_and_stewardship_round_trip(self, tmp_path) -> None:
        # A default-kind edge stays a bare id on disk; a typed edge serializes as
        # a {to, kind} mapping. owner/verified round-trip when set.
        store = MarkdownDocumentFileStore(tmp_path)
        doc = _doc(
            related=(RelatedRef("adr-0002"), RelatedRef("adr-0003", "supersedes")),
            owner="platform-team",
            verified=date(2026, 6, 1),
        )
        rel = store.write(doc)
        raw = (tmp_path / rel).read_text(encoding="utf-8")
        assert "- adr-0002\n" in raw  # bare id for the default kind
        assert "kind: supersedes" in raw  # typed edge as a mapping
        loaded = store.read(rel)
        assert loaded.related == (RelatedRef("adr-0002"), RelatedRef("adr-0003", "supersedes"))
        assert loaded.owner == "platform-team"
        assert loaded.verified == date(2026, 6, 1)

    def test_code_globs_round_trip_and_are_absent_when_empty(self, tmp_path) -> None:
        # The governed globs are frontmatter like any other field, and a
        # document governing nothing carries no `code:` key at all — the same
        # rule owner/verified follow, so files stay minimal (issue-90aea6d1b891).
        store = MarkdownDocumentFileStore(tmp_path)
        rel = store.write(_doc(code=("src/docir/platform/persistence/**", "docs/*.md")))
        raw = (tmp_path / rel).read_text(encoding="utf-8")
        assert "- src/docir/platform/persistence/**\n" in raw
        loaded = store.read(rel)
        # Author order, not sorted: the file is what the human wrote.
        assert loaded.code == ("src/docir/platform/persistence/**", "docs/*.md")

        bare = store.write(_doc(id="adr-0009", code=()))
        assert "code:" not in (tmp_path / bare).read_text(encoding="utf-8")
        assert store.read(bare).code == ()

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

    def test_related_mapping_without_target_is_malformed(self, tmp_path) -> None:
        store = MarkdownDocumentFileStore(tmp_path)
        bad = tmp_path / "decisions" / "adr-0001-bad.md"
        bad.parent.mkdir(parents=True)
        bad.write_text(
            "---\nid: adr-0001\ntitle: T\ndescription: d\ntype: decision\n"
            "status: proposed\ncreated: '2026-01-01'\nupdated: '2026-01-01'\n"
            "tags: []\nrelated:\n- kind: supersedes\n---\n\nbody\n",  # no 'to'
            encoding="utf-8",
        )
        with pytest.raises(ValidationError):
            store.read("decisions/adr-0001-bad.md")

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

    def test_read_malformed_frontmatter_raises_validation(self, tmp_path) -> None:
        # F2: a bad date must surface as a clean ValidationError, not a raw
        # ValueError leaking out of the parser.
        store = MarkdownDocumentFileStore(tmp_path)
        bad = tmp_path / "decisions" / "adr-9999-bad.md"
        bad.parent.mkdir(parents=True)
        bad.write_text(_MALFORMED, encoding="utf-8")
        with pytest.raises(ValidationError):
            store.read("decisions/adr-9999-bad.md")

    def test_scan_skips_malformed_and_find_reports_it(self, tmp_path) -> None:
        # F2: one unparseable file must not abort the whole scan; it is reported
        # separately via find_malformed.
        store = MarkdownDocumentFileStore(tmp_path)
        store.write(_doc())  # a valid file
        (tmp_path / "decisions" / "adr-9999-bad.md").write_text(_MALFORMED, encoding="utf-8")
        assert {d.id for d in store.scan()} == {"adr-0001"}  # malformed skipped
        assert any("adr-9999-bad.md" in path for path, _reason in store.find_malformed())


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
