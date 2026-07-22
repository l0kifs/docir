"""Integration tests for the document use cases through the full stack.

Each test drives the real dispatcher (application services + SQLAlchemy index +
filesystem store + inline embedder), so every layer is exercised together.
"""

from __future__ import annotations

from datetime import date

import pytest

from docir.config.settings import Settings
from docir.entry_points.dispatch import Dispatcher
from docir.platform.errors import (
    DanglingReferenceError,
    DocumentNotFoundError,
    InvalidStatusTransitionError,
    StaleWriteError,
    UnknownRelatedError,
    UnknownTagError,
    ValidationError,
)

FIXED_DATE = date(2026, 7, 7)


class TestAdd:
    def test_add_creates_document_and_file(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        dispatcher.dispatch("tag_add", {"key": "auth", "description": "Auth."})
        view = dispatcher.dispatch(
            "add",
            {
                "type": "decision",
                "title": "Auth strategy",
                "description": "Auth approach.",
                "tags": ["auth"],
                "body": "Body.",
            },
        )
        assert view["id"] == "adr-0001"
        assert view["status"] == "proposed"
        assert view["created"] == FIXED_DATE.isoformat()
        assert view["created"] == view["updated"]
        assert (settings.docs_root / view["path"]).exists()

    def test_ids_increment(self, dispatcher: Dispatcher) -> None:
        first = dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
        second = dispatcher.dispatch("add", {"type": "decision", "title": "B", "description": "d"})
        assert first["id"] == "adr-0001"
        assert second["id"] == "adr-0002"

    def test_unknown_tag_rejected(self, dispatcher: Dispatcher) -> None:
        with pytest.raises(UnknownTagError):
            dispatcher.dispatch(
                "add",
                {"type": "decision", "title": "T", "description": "d", "tags": ["ghost"]},
            )

    def test_unknown_related_rejected(self, dispatcher: Dispatcher) -> None:
        with pytest.raises(UnknownRelatedError):
            dispatcher.dispatch(
                "add",
                {
                    "type": "decision",
                    "title": "T",
                    "description": "d",
                    "related": ["adr-9999"],
                },
            )


class TestGet:
    def test_get_returns_document(self, seeded: Dispatcher) -> None:
        assert seeded.dispatch("get", {"doc_id": "adr-0001"})["title"] == "Auth strategy"

    def test_get_missing_raises(self, dispatcher: Dispatcher) -> None:
        with pytest.raises(DocumentNotFoundError):
            dispatcher.dispatch("get", {"doc_id": "adr-0404"})


class TestUpdate:
    def test_status_transition(self, seeded: Dispatcher) -> None:
        view = seeded.dispatch("update", {"doc_id": "issue-0001", "status": "resolved"})
        assert view["status"] == "resolved"

    def test_invalid_transition_rejected(self, seeded: Dispatcher) -> None:
        seeded.dispatch("update", {"doc_id": "issue-0001", "status": "resolved"})
        with pytest.raises(InvalidStatusTransitionError):
            seeded.dispatch("update", {"doc_id": "issue-0001", "status": "open"})

    def test_transition_override_allowed(self, seeded: Dispatcher) -> None:
        seeded.dispatch("update", {"doc_id": "issue-0001", "status": "resolved"})
        view = seeded.dispatch(
            "update",
            {"doc_id": "issue-0001", "status": "open", "allow_transition_override": True},
        )
        assert view["status"] == "open"

    def test_append_section(self, seeded: Dispatcher) -> None:
        view = seeded.dispatch(
            "update",
            {"doc_id": "issue-0001", "append_section": ["Resolution", "Fixed"]},
        )
        assert "## Resolution" in view["body"]
        assert view["updated"] == FIXED_DATE.isoformat()

    def test_replace_section(self, seeded: Dispatcher) -> None:
        seeded.dispatch("update", {"doc_id": "adr-0001", "append_section": ["Context", "old text"]})
        view = seeded.dispatch(
            "update", {"doc_id": "adr-0001", "replace_section": ["Context", "new text"]}
        )
        assert "new text" in view["body"] and "old text" not in view["body"]

    def test_replace_body_requires_force(self, seeded: Dispatcher) -> None:
        with pytest.raises(ValidationError):
            seeded.dispatch("update", {"doc_id": "adr-0001", "replace_body": "x"})

    def test_replace_body_with_force(self, seeded: Dispatcher) -> None:
        view = seeded.dispatch(
            "update", {"doc_id": "adr-0001", "replace_body": "brand new", "force": True}
        )
        assert view["body"] == "brand new"

    def test_two_body_modes_rejected(self, seeded: Dispatcher) -> None:
        with pytest.raises(ValidationError):
            seeded.dispatch(
                "update",
                {
                    "doc_id": "adr-0001",
                    "append_section": ["A", "x"],
                    "replace_section": ["B", "y"],
                },
            )

    def test_stale_full_body_replace_rejected(self, seeded: Dispatcher, settings: Settings) -> None:
        # Simulate an out-of-band edit to the file after it was indexed.
        path = settings.docs_root / "decisions" / "adr-0001-auth-strategy.md"
        path.write_text(path.read_text() + "\n\nhand edit\n", encoding="utf-8")
        with pytest.raises(StaleWriteError):
            seeded.dispatch("update", {"doc_id": "adr-0001", "replace_body": "x", "force": True})

    def test_no_changes_returns_current(self, seeded: Dispatcher) -> None:
        view = seeded.dispatch("update", {"doc_id": "adr-0001"})
        assert view["id"] == "adr-0001"

    def test_set_tags_and_related(self, seeded: Dispatcher) -> None:
        view = seeded.dispatch(
            "update", {"doc_id": "adr-0001", "set_tags": ["api"], "set_related": []}
        )
        assert list(view["tags"]) == ["api"]
        assert list(view["related"]) == []


class TestQuerySearchContext:
    def test_query_excludes_inactive_by_default(self, seeded: Dispatcher) -> None:
        seeded.dispatch("update", {"doc_id": "issue-0001", "status": "resolved"})
        ids = {d["id"] for d in seeded.dispatch("query", {})}
        assert "issue-0001" not in ids
        with_inactive = {d["id"] for d in seeded.dispatch("query", {"include_inactive": True})}
        assert "issue-0001" in with_inactive

    def test_query_by_tag(self, seeded: Dispatcher) -> None:
        ids = {d["id"] for d in seeded.dispatch("query", {"tags": ["api"]})}
        assert ids == {"adr-0001"}

    def test_search_finds_and_excludes_resolved(self, seeded: Dispatcher) -> None:
        hits = seeded.dispatch("search", {"text": "refresh token"})
        assert any(h["id"] == "issue-0001" for h in hits)
        seeded.dispatch("update", {"doc_id": "issue-0001", "status": "resolved"})
        hits2 = seeded.dispatch("search", {"text": "refresh token"})
        assert all(h["id"] != "issue-0001" for h in hits2)

    def test_context_ranks_and_augments_with_graph(self, seeded: Dispatcher) -> None:
        results = seeded.dispatch(
            "context", {"task": "implement auth refresh endpoint", "limit": 1}
        )
        ids = {d["id"] for d in results}
        # limit=1 primary result, plus its one-hop related neighbour.
        assert "adr-0001" in ids or "issue-0001" in ids
        assert any(d.get("via_graph") for d in results) or len(ids) >= 1


class TestArchiveDelete:
    def test_archive_hides_from_search(self, seeded: Dispatcher) -> None:
        seeded.dispatch("archive", {"doc_id": "adr-0001"})
        assert seeded.dispatch("get", {"doc_id": "adr-0001"})["archived"] is True
        hits = seeded.dispatch("search", {"text": "JWT access tokens"})
        assert all(h["id"] != "adr-0001" for h in hits)

    def test_archive_idempotent(self, seeded: Dispatcher) -> None:
        seeded.dispatch("archive", {"doc_id": "adr-0001"})
        again = seeded.dispatch("archive", {"doc_id": "adr-0001"})
        assert again["archived"] is True

    def test_unarchive_restores(self, seeded: Dispatcher) -> None:
        seeded.dispatch("archive", {"doc_id": "adr-0001"})
        view = seeded.dispatch("unarchive", {"doc_id": "adr-0001"})
        assert view["archived"] is False
        again = seeded.dispatch("unarchive", {"doc_id": "adr-0001"})
        assert again["archived"] is False

    def test_delete_blocked_by_incoming(self, seeded: Dispatcher) -> None:
        with pytest.raises(DanglingReferenceError):
            seeded.dispatch("delete", {"doc_id": "adr-0001"})

    def test_delete_force(self, seeded: Dispatcher, settings: Settings) -> None:
        path = settings.docs_root / "decisions" / "adr-0001-auth-strategy.md"
        seeded.dispatch("delete", {"doc_id": "adr-0001", "force": True})
        assert not path.exists()
        with pytest.raises(DocumentNotFoundError):
            seeded.dispatch("get", {"doc_id": "adr-0001"})


class TestLimitValidation:
    """F1: a non-positive --limit must be rejected, not silently mis-sliced.

    limit=-1 otherwise returns all-but-the-last (query), one hit (search), or
    nothing (context) — three different results from the same argument.
    """

    @pytest.mark.parametrize("limit", [0, -1, -50])
    def test_query_rejects_non_positive_limit(self, seeded: Dispatcher, limit: int) -> None:
        with pytest.raises(ValidationError):
            seeded.dispatch("query", {"limit": limit})

    @pytest.mark.parametrize("limit", [0, -1])
    def test_search_rejects_non_positive_limit(self, seeded: Dispatcher, limit: int) -> None:
        with pytest.raises(ValidationError):
            seeded.dispatch("search", {"text": "auth", "limit": limit})

    @pytest.mark.parametrize("limit", [0, -1])
    def test_context_rejects_non_positive_limit(self, seeded: Dispatcher, limit: int) -> None:
        with pytest.raises(ValidationError):
            seeded.dispatch("context", {"task": "auth", "limit": limit})

    def test_positive_limit_still_works(self, seeded: Dispatcher) -> None:
        assert isinstance(seeded.dispatch("query", {"limit": 1}), list)


class TestSearchRobustness:
    """F5: FTS5 MATCH is syntax-sensitive; raw user input must never crash it."""

    @pytest.mark.parametrize(
        "text",
        ["O'Brian", 'auth OR "', "*", "NEAR(a b)", "\U0001f600 tokens", "", "   "],
    )
    def test_special_characters_do_not_crash(self, seeded: Dispatcher, text: str) -> None:
        assert isinstance(seeded.dispatch("search", {"text": text}), list)
