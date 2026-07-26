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
    UnknownRelationKindError,
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

    def test_set_owner_and_mark_verified(self, seeded: Dispatcher) -> None:
        view = seeded.dispatch(
            "update", {"doc_id": "adr-0001", "set_owner": "platform-team", "mark_verified": True}
        )
        assert view["owner"] == "platform-team"
        assert view["verified"] == FIXED_DATE.isoformat()


class TestTypedEdges:
    def test_typed_edge_round_trips(self, seeded: Dispatcher) -> None:
        view = seeded.dispatch(
            "add",
            {
                "type": "decision",
                "title": "Successor",
                "description": "d",
                "related": ["adr-0001:supersedes"],
            },
        )
        assert list(view["related"]) == [{"target": "adr-0001", "kind": "supersedes"}]

    def test_bare_id_defaults_to_relates_to(self, seeded: Dispatcher) -> None:
        view = seeded.dispatch(
            "add",
            {"type": "decision", "title": "Linked", "description": "d", "related": ["adr-0001"]},
        )
        assert view["related"][0]["kind"] == "relates_to"

    def test_unknown_relation_kind_rejected(self, seeded: Dispatcher) -> None:
        with pytest.raises(UnknownRelationKindError):
            seeded.dispatch(
                "add",
                {
                    "type": "decision",
                    "title": "Bad",
                    "description": "d",
                    "related": ["adr-0001:teleports_to"],
                },
            )


class TestSkeletonReadPaths:
    """The two-tier contract: list paths omit the body; `get` carries it."""

    def test_query_and_search_and_context_omit_body(self, seeded: Dispatcher) -> None:
        for command, payload in (
            ("query", {}),
            ("search", {"text": "auth"}),
            ("context", {"task": "auth refresh"}),
        ):
            results = seeded.dispatch(command, payload)
            assert results, f"{command} returned nothing"
            for row in results:
                assert "body" not in row, f"{command} leaked a body into the skeleton"
                assert "title" in row and "description" in row

    def test_get_includes_body(self, seeded: Dispatcher) -> None:
        full = seeded.dispatch("get", {"doc_id": "adr-0001"})
        assert full.get("body")


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
            "context", {"task": "implement auth refresh endpoint", "limit": 2}
        )
        ids = {d["id"] for d in results}
        assert "adr-0001" in ids or "issue-0001" in ids
        assert any(d.get("via_graph") for d in results) or len(ids) >= 1


class TestContextBudget:
    """``--limit`` is a hard ceiling on the response (guards GAP-005).

    Graph expansion used to run *after* the limit and was itself uncapped, so a
    densely linked corpus blew straight through it: three seeds with out-degree
    two returned nine documents from ``--limit 3``. That contradicts the entire
    point of the limit for a token-budgeted agent.
    """

    @staticmethod
    def _linked_corpus(dispatcher: Dispatcher, decisions: int, per_decision: int) -> None:
        """N decisions, each pointing at ``per_decision`` issues of its own."""
        for d in range(decisions):
            related = []
            for i in range(per_decision):
                issue = dispatcher.dispatch(
                    "add",
                    {
                        "type": "issue",
                        "title": f"cache issue {d}-{i}",
                        "description": "cache invalidation problem",
                    },
                )
                related.append(issue["id"])
            dispatcher.dispatch(
                "add",
                {
                    "type": "decision",
                    "title": f"cache policy {d}",
                    "description": "cache invalidation policy",
                    "related": related,
                },
            )

    def test_limit_is_never_exceeded(self, dispatcher: Dispatcher) -> None:
        # The exact shape that returned 9 for --limit 3 before the fix.
        self._linked_corpus(dispatcher, decisions=3, per_decision=2)
        results = dispatcher.dispatch("context", {"task": "cache invalidation policy", "limit": 3})
        assert len(results) == 3

    def test_expand_zero_disables_graph_neighbours(self, dispatcher: Dispatcher) -> None:
        self._linked_corpus(dispatcher, decisions=3, per_decision=2)
        results = dispatcher.dispatch(
            "context", {"task": "cache invalidation policy", "limit": 4, "expand": 0}
        )
        assert len(results) == 4
        assert not any(d.get("via_graph") for d in results)

    def test_expand_reserves_slots_for_neighbours(self, dispatcher: Dispatcher) -> None:
        self._linked_corpus(dispatcher, decisions=3, per_decision=2)
        results = dispatcher.dispatch(
            "context", {"task": "cache invalidation policy", "limit": 4, "expand": 2}
        )
        assert len(results) == 4
        assert sum(1 for d in results if d.get("via_graph")) <= 2

    def test_unused_neighbour_slots_are_backfilled(self, dispatcher: Dispatcher) -> None:
        # No relations at all, so expansion contributes nothing; the response
        # must still be full rather than short by the reserved slots.
        for i in range(6):
            dispatcher.dispatch(
                "add",
                {"type": "decision", "title": f"policy {i}", "description": "cache policy"},
            )
        results = dispatcher.dispatch("context", {"task": "cache policy", "limit": 5, "expand": 2})
        assert len(results) == 5
        assert not any(d.get("via_graph") for d in results)

    def test_limit_one_still_returns_a_ranked_hit(self, dispatcher: Dispatcher) -> None:
        # expand must never crowd out the seed it is expanding from.
        self._linked_corpus(dispatcher, decisions=2, per_decision=2)
        results = dispatcher.dispatch(
            "context", {"task": "cache invalidation policy", "limit": 1, "expand": 5}
        )
        assert len(results) == 1
        assert not results[0].get("via_graph")


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
