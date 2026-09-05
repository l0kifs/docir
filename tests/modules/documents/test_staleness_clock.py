"""The staleness clock runs from `created`, never from the last edit.

`stale_reference_date()` used to fall back to `updated` when a document carried
no `verified`, and every edit moves `updated` (issue-6726eabcf871). So a
document nobody had vouched for left the review queue the moment somebody wrote
in it — and the body most likely to be written into an overdue document is the
re-check saying it is *still* unanswered. Recording the silence ended the report
of it.

adr-fad49eaa4648 ages from `created` instead: the one date the write path sets
once and never rewrites. These tests are the reporter's reproduction — an
overdue document, an edit that is not a verification, and the queue still
holding it afterwards — plus the two clocks that must keep working.
"""

from __future__ import annotations

from datetime import date

import pytest

from docir.config.settings import Settings
from docir.entry_points.dispatch import Dispatcher

#: The suite's `FixedClock` date. Every write below stamps `updated` with it.
TODAY = date(2026, 7, 7)


def _overdue_decision(settings: Settings, doc_id: str = "adr-0001") -> None:
    """A decision written long before its 365-day cadence, never verified."""
    decisions = settings.docs_root / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    (decisions / f"{doc_id}-ask.md").write_text(
        "---\n"
        "created: '2024-01-01'\n"
        "description: an ask made of another team\n"
        f"id: {doc_id}\n"
        "related: []\n"
        "status: proposed\n"
        "tags: []\n"
        "title: Ask sent to the platform team\n"
        "type: decision\n"
        "updated: '2024-01-01'\n"
        "---\n\nThe ask was sent.\n",
        encoding="utf-8",
    )


def _stale_ids(dispatcher: Dispatcher) -> set[str]:
    return {
        issue["doc_ids"][0]
        for issue in dispatcher.dispatch("check", {})
        if issue["kind"] == "stale"
    }


@pytest.fixture
def overdue(dispatcher: Dispatcher, settings: Settings) -> Dispatcher:
    _overdue_decision(settings)
    dispatcher.dispatch("reindex", {})
    return dispatcher


class TestAnEditDoesNotClearTheQueue:
    """The reported defect: writing the re-check emptied the queue."""

    def test_the_queue_holds_it_before_the_edit(self, overdue: Dispatcher) -> None:
        assert _stale_ids(overdue) == {"adr-0001"}
        assert overdue.dispatch("get", {"doc_id": "adr-0001"})["stale"] is True

    def test_recording_the_re_check_leaves_it_in_the_queue(self, overdue: Dispatcher) -> None:
        overdue.dispatch(
            "update",
            {
                "doc_id": "adr-0001",
                "append_section": ["Re-checks", "Escalated to the team lead. Still no answer."],
            },
        )

        view = overdue.dispatch("get", {"doc_id": "adr-0001"})
        # The edit did happen, and it did move the edit clock...
        assert "Re-checks" in view["body"]
        assert view["updated"] == TODAY.isoformat()
        # ...and none of that is a verification.
        assert view["verified"] is None
        assert view["stale"] is True
        assert _stale_ids(overdue) == {"adr-0001"}

    def test_the_review_queue_query_still_returns_it(self, overdue: Dispatcher) -> None:
        overdue.dispatch(
            "update", {"doc_id": "adr-0001", "append_section": ["Re-checks", "no answer"]}
        )

        queue = overdue.dispatch("query", {"stale": True})
        assert [row["id"] for row in queue] == ["adr-0001"]

    def test_repeated_re_checks_never_clear_it(self, overdue: Dispatcher) -> None:
        # The failure got *more* reliable the longer a document went unanswered,
        # because each re-check was another edit.
        for nth in range(3):
            overdue.dispatch(
                "update",
                {"doc_id": "adr-0001", "append_section": [f"Check {nth}", "still nothing"]},
            )
            assert _stale_ids(overdue) == {"adr-0001"}

    def test_other_frontmatter_edits_do_not_clear_it_either(self, overdue: Dispatcher) -> None:
        # The scope is every write, not the body ones: `--set-owner` is the
        # first thing done to a document a review queue just surfaced.
        overdue.dispatch("update", {"doc_id": "adr-0001", "set_owner": "platform-team"})
        assert _stale_ids(overdue) == {"adr-0001"}

        overdue.dispatch("tag_add", {"key": "integrity", "description": "Corpus integrity."})
        overdue.dispatch("update", {"doc_id": "adr-0001", "set_tags": ["integrity"]})
        assert _stale_ids(overdue) == {"adr-0001"}


class TestVerificationIsStillTheOnlyWayOut:
    def test_verifying_clears_it(self, overdue: Dispatcher) -> None:
        overdue.dispatch("update", {"doc_id": "adr-0001", "mark_verified": True})

        view = overdue.dispatch("get", {"doc_id": "adr-0001"})
        assert view["verified"] == TODAY.isoformat()
        assert view["stale"] is False
        assert _stale_ids(overdue) == set()

    def test_a_stale_verification_puts_it_back(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # `verified` still wins over `created` when it is present — including
        # when it is itself past the cadence, which is the ordinary case.
        decisions = settings.docs_root / "decisions"
        decisions.mkdir(parents=True, exist_ok=True)
        (decisions / "adr-0002-old.md").write_text(
            "---\n"
            "created: '2026-07-01'\n"
            "description: verified long ago\n"
            "id: adr-0002\n"
            "related: []\n"
            "status: proposed\n"
            "tags: []\n"
            "title: Verified once, long ago\n"
            "type: decision\n"
            "updated: '2026-07-01'\n"
            "verified: '2024-01-01'\n"
            "---\n\nbody\n",
            encoding="utf-8",
        )
        dispatcher.dispatch("reindex", {})

        # Recently created, recently edited, verified two years ago: stale.
        assert _stale_ids(dispatcher) == {"adr-0002"}


class TestANewDocumentIsNotStale:
    """The cadence still runs; `created` does not mean "stale from birth".

    Treating an absent `verified` as infinitely stale was the other candidate
    fix, and it reports 83 of this store's 84 cadence-bearing documents —
    documents written the day before included (adr-fad49eaa4648).
    """

    def test_a_document_written_today_is_not_in_the_queue(self, dispatcher: Dispatcher) -> None:
        dispatcher.dispatch(
            "add", {"type": "decision", "title": "Fresh", "description": "d", "body": "x"}
        )
        assert _stale_ids(dispatcher) == set()


class TestTheFindingNamesItsClock:
    def test_a_never_verified_document_says_so(self, overdue: Dispatcher) -> None:
        message = next(
            issue["message"] for issue in overdue.dispatch("check", {}) if issue["kind"] == "stale"
        )
        assert "never verified" in message
        assert "created 2024-01-01" in message
        # And says what clears it, since `--verified` is the only thing that does.
        assert "docir update adr-0001 --verified" in message
