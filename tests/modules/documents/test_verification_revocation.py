"""A verification is withdrawn when the content it covered moves.

Two halves of one rule (adr-f4e6ade4afd0). `update --clear-verified` is the way back
from a stamp that asserts a review nobody did — before it, the only recovery was
the hand-edit the CLI exists to prevent, and `docir check` then reported the
hand-edit (issue-b4813930bfca). And an edit to the title, the description or
the body of a verified document does the same thing by itself: what somebody
read is not what is there now.

Both stamp `revoked`, and the cadence restarts from it. The rule that keeps
issue-6726eabcf871 closed is that only a *standing* verification can be
withdrawn: an edit to a document nobody has vouched for moves nothing, so
writing "still unanswered" into an overdue document still cannot clear the
queue.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from conftest import FixedClock
from docir.config.settings import Settings
from docir.entry_points.composition import build_container
from docir.entry_points.dispatch import Dispatcher
from docir.platform.errors import ValidationError

#: A second type over the frozen core, so a retype has somewhere to go.
SCHEMA_WITH_A_SECOND_TYPE = """\
profiles: [software]

types:
  note:
    prefix: note
    level: 1
    default_status: draft
    statuses:
      draft: [active]
      active: []
"""

#: The suite's `FixedClock` date.
TODAY = date(2026, 7, 7)


def _verified_decision(dispatcher: Dispatcher, title: str = "Rotation") -> str:
    """A decision verified today, with a body worth re-reading."""
    view = dispatcher.dispatch(
        "add",
        {
            "type": "decision",
            "title": title,
            "description": "how the key is rotated",
            "body": "## Rotation\n\nThe key is rotated by hand.\n",
        },
    )
    dispatcher.dispatch("update", {"doc_id": view["id"], "mark_verified": True})
    return str(view["id"])


def _stale_findings(dispatcher: Dispatcher) -> list[dict]:
    return [issue for issue in dispatcher.dispatch("check", {}) if issue["kind"] == "stale"]


class TestClearVerified:
    """The reported issue: nothing could take a stamp back."""

    def test_it_erases_the_stamp_and_leaves_no_review_window(self, dispatcher: Dispatcher) -> None:
        # No `revoked` either: a claim nobody made buys nothing. Stamping one
        # would hand the document a fresh cadence for the act of admitting the
        # stamp was wrong, which is worse than leaving the wrong stamp in place.
        doc_id = _verified_decision(dispatcher)
        assert dispatcher.dispatch("get", {"doc_id": doc_id})["verified"] == TODAY.isoformat()

        view = dispatcher.dispatch("update", {"doc_id": doc_id, "clear_verified": True})

        assert view["verified"] is None
        assert view["revoked"] is None

    def test_a_bad_stamp_on_an_old_document_returns_it_to_the_queue(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # The reporter's case end to end: a document written long ago, stamped
        # by mistake, is overdue again the moment the stamp is withdrawn.
        decisions = settings.docs_root / "decisions"
        decisions.mkdir(parents=True, exist_ok=True)
        (decisions / "adr-0001-old.md").write_text(
            "---\ncreated: '2023-01-01'\ndescription: written long ago\nid: adr-0001\n"
            "related: []\nstatus: proposed\ntags: []\ntitle: An old decision\n"
            "type: decision\nupdated: '2023-01-01'\nverified: '2026-07-01'\n---\n\nbody\n",
            encoding="utf-8",
        )
        dispatcher.dispatch("reindex", {})
        assert dispatcher.dispatch("get", {"doc_id": "adr-0001"})["stale"] is False

        dispatcher.dispatch("update", {"doc_id": "adr-0001", "clear_verified": True})

        assert dispatcher.dispatch("get", {"doc_id": "adr-0001"})["stale"] is True
        assert _stale_findings(dispatcher)[0]["message"].count("never verified") == 1

    def test_the_file_says_so_too(self, dispatcher: Dispatcher, settings: Settings) -> None:
        # Not only the index: the file is the source of truth, and the reporter's
        # workaround was to edit it by hand. What the CLI writes has to be what a
        # teammate reads in the diff.
        doc_id = _verified_decision(dispatcher)
        dispatcher.dispatch("update", {"doc_id": doc_id, "clear_verified": True})

        text = next((settings.docs_root / "decisions").glob(f"{doc_id}-*.md")).read_text()
        assert "verified:" not in text
        assert "revoked:" not in text
        assert "verified_content:" not in text

    def test_check_is_clean_afterwards(self, dispatcher: Dispatcher) -> None:
        # The whole point of the flag: the hand-edit it replaces produced a
        # finding of its own, so the fix for a bad stamp used to cost a warning.
        doc_id = _verified_decision(dispatcher)
        dispatcher.dispatch("update", {"doc_id": doc_id, "clear_verified": True})

        assert dispatcher.dispatch("check", {}) == [] or all(
            issue["kind"] not in {"malformed", "duplicate-id"}
            for issue in dispatcher.dispatch("check", {})
        )

    def test_it_survives_a_rebuilt_index(self, dispatcher: Dispatcher) -> None:
        doc_id = _verified_decision(dispatcher)
        dispatcher.dispatch("update", {"doc_id": doc_id, "set_title": "Key rotation"})
        dispatcher.dispatch("reindex", {})

        view = dispatcher.dispatch("get", {"doc_id": doc_id})
        assert view["revoked"] == TODAY.isoformat()
        assert view["verified"] is None

    def test_it_is_refused_when_nothing_is_standing(self, dispatcher: Dispatcher) -> None:
        # Nothing to withdraw. Silently succeeding would let a sweep report that
        # it took back claims that were never made.
        view = dispatcher.dispatch(
            "add", {"type": "decision", "title": "Never vouched for", "description": "d"}
        )
        with pytest.raises(ValidationError, match="no verification to withdraw"):
            dispatcher.dispatch("update", {"doc_id": view["id"], "clear_verified": True})

        assert dispatcher.dispatch("get", {"doc_id": view["id"]})["revoked"] is None

    def test_withdrawing_an_already_revoked_one_names_the_revocation(
        self, dispatcher: Dispatcher
    ) -> None:
        doc_id = _verified_decision(dispatcher)
        dispatcher.dispatch("update", {"doc_id": doc_id, "set_title": "Key rotation"})

        with pytest.raises(ValidationError, match=f"already revoked on {TODAY.isoformat()}"):
            dispatcher.dispatch("update", {"doc_id": doc_id, "clear_verified": True})

    def test_it_is_refused_alongside_a_verification(self, dispatcher: Dispatcher) -> None:
        doc_id = _verified_decision(dispatcher)
        with pytest.raises(ValidationError, match="opposite"):
            dispatcher.dispatch(
                "update", {"doc_id": doc_id, "mark_verified": True, "clear_verified": True}
            )

    def test_verifying_again_clears_the_revocation(self, dispatcher: Dispatcher) -> None:
        # Otherwise the file carries a date saying this document's verification
        # was withdrawn, under a `verified:` line saying it stands.
        doc_id = _verified_decision(dispatcher)
        dispatcher.dispatch("update", {"doc_id": doc_id, "set_title": "Key rotation"})

        view = dispatcher.dispatch("update", {"doc_id": doc_id, "mark_verified": True})
        assert view["verified"] == TODAY.isoformat()
        assert view["revoked"] is None


class TestAContentEditWithdrawsIt:
    """The stamp covers the content; the content moved."""

    @pytest.mark.parametrize(
        "patch",
        [
            pytest.param({"append_section": ["Notes", "rotated by the operator now"]}, id="append"),
            pytest.param(
                {"replace_section": ["Rotation", "The key rotates on a schedule."]}, id="replace"
            ),
            pytest.param({"remove_section": "Rotation"}, id="remove"),
            pytest.param({"set_title": "Key rotation"}, id="title"),
            pytest.param({"set_description": "how the key rotates now"}, id="description"),
        ],
    )
    def test_editing_what_was_read_revokes_it(
        self, dispatcher: Dispatcher, patch: dict[str, object]
    ) -> None:
        doc_id = _verified_decision(dispatcher)

        view = dispatcher.dispatch("update", {"doc_id": doc_id, **patch})

        assert view["verified"] is None
        assert view["revoked"] == TODAY.isoformat()

    @pytest.mark.parametrize(
        "patch",
        [
            pytest.param({"status": "accepted"}, id="status"),
            pytest.param({"set_owner": "platform-team"}, id="owner"),
            pytest.param({"set_code": ["src/auth/**"]}, id="code"),
            pytest.param({"set_isolated": "standalone"}, id="isolated"),
        ],
    )
    def test_metadata_leaves_it_standing(
        self, dispatcher: Dispatcher, patch: dict[str, object]
    ) -> None:
        # None of these changes a word of what the reviewer read. Revoking on
        # them would make the stamp unkeepable: a status is what moves on a
        # document somebody has just finished reviewing.
        doc_id = _verified_decision(dispatcher)

        view = dispatcher.dispatch("update", {"doc_id": doc_id, **patch})

        assert view["verified"] == TODAY.isoformat()
        assert view["revoked"] is None

    def test_a_retype_leaves_it_standing(self, settings: Settings) -> None:
        # A retype is not a content change (adr-f8cce745d0d5): it does not
        # re-embed, and it does not withdraw a verification either. Its own
        # schema, because the frozen core declares only one type.
        settings.ensure_directories()
        settings.schema_path.write_text(SCHEMA_WITH_A_SECOND_TYPE, encoding="utf-8")
        container = build_container(settings, background_embeddings=False, clock=FixedClock())
        try:
            docs = container.dispatcher
            doc_id = _verified_decision(docs)

            view = docs.dispatch(
                "update", {"doc_id": doc_id, "set_type": "note", "status": "draft"}
            )

            assert view["type"] == "note"
            assert view["verified"] == TODAY.isoformat()
            assert view["revoked"] is None
        finally:
            container.close()

    def test_verifying_with_the_edit_keeps_the_stamp(self, dispatcher: Dispatcher) -> None:
        # "I rewrote it and re-read it" — the explicit flag beats the inferred
        # withdrawal, or the one call that is honest about both halves of the
        # work would be the one call that cannot record it.
        doc_id = _verified_decision(dispatcher)

        view = dispatcher.dispatch(
            "update",
            {
                "doc_id": doc_id,
                "replace_section": ["Rotation", "The key rotates on a schedule."],
                "mark_verified": True,
            },
        )

        assert view["verified"] == TODAY.isoformat()
        assert view["revoked"] is None

    def test_an_unverified_document_is_left_alone(self, dispatcher: Dispatcher) -> None:
        # The rule that keeps issue-6726eabcf871 closed. Stamping `revoked` on
        # every edit would hand each one a fresh cadence, and the review queue
        # would empty itself again — this time through the new field.
        view = dispatcher.dispatch(
            "add", {"type": "decision", "title": "Open ask", "description": "unanswered"}
        )
        doc_id = view["id"]

        after = dispatcher.dispatch(
            "update", {"doc_id": doc_id, "append_section": ["Re-checks", "still no answer"]}
        )

        assert after["verified"] is None
        assert after["revoked"] is None

    def test_a_second_edit_does_not_move_the_clock_again(self, settings: Settings) -> None:
        # One verification buys one reset. The document is unverified after the
        # first edit, so every edit after it is the case above — and a corpus
        # edited weekly would otherwise never come due.
        #
        # Two containers on two dates: on one frozen clock a second stamp is
        # indistinguishable from the first, so the test could not fail.
        settings.ensure_directories()
        first = build_container(settings, background_embeddings=False, clock=FixedClock())
        try:
            docs = first.dispatcher
            doc_id = _verified_decision(docs)
            docs.dispatch("update", {"doc_id": doc_id, "set_title": "Key rotation"})
            assert docs.dispatch("get", {"doc_id": doc_id})["revoked"] == TODAY.isoformat()
        finally:
            first.close()

        later = build_container(
            settings, background_embeddings=False, clock=FixedClock(date(2026, 9, 1))
        )
        try:
            docs = later.dispatcher
            docs.dispatch("update", {"doc_id": doc_id, "set_title": "Rotating the key"})

            view = docs.dispatch("get", {"doc_id": doc_id})
            assert view["updated"] == "2026-09-01"
            assert view["revoked"] == TODAY.isoformat()
        finally:
            later.close()


class TestTheClockRunsFromTheRevocation:
    """A withdrawn verification restarts the cadence; it does not erase it."""

    def _decision(self, settings: Settings, doc_id: str, **frontmatter: str) -> None:
        decisions = settings.docs_root / "decisions"
        decisions.mkdir(parents=True, exist_ok=True)
        lines = "".join(f"{key}: '{value}'\n" for key, value in sorted(frontmatter.items()))
        (decisions / f"{doc_id}-old.md").write_text(
            "---\n"
            f"created: '2023-01-01'\n"
            "description: written long ago\n"
            f"id: {doc_id}\n"
            "related: []\n"
            "status: proposed\n"
            "tags: []\n"
            "title: An old decision\n"
            "type: decision\n"
            "updated: '2023-01-01'\n"
            f"{lines}"
            "---\n\n## Rotation\n\nThe key is rotated by hand.\n",
            encoding="utf-8",
        )

    def test_an_edit_does_not_make_an_old_document_stale_on_the_spot(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # The alternative reading — drop `verified` and fall back to `created` —
        # reports this document overdue the instant the edit lands, three years
        # after it was written and seconds after somebody improved it. That is
        # the failure adr-fad49eaa4648 measured on the other clock.
        self._decision(settings, "adr-0001", verified="2026-07-01")
        dispatcher.dispatch("reindex", {})

        dispatcher.dispatch("update", {"doc_id": "adr-0001", "set_title": "Rotating the key"})

        view = dispatcher.dispatch("get", {"doc_id": "adr-0001"})
        assert view["verified"] is None
        assert view["revoked"] == TODAY.isoformat()
        assert view["stale"] is False
        assert _stale_findings(dispatcher) == []

    def test_the_cadence_catches_up_with_the_revocation(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # And it is a restart, not an exemption: a revocation older than the
        # cadence is overdue, exactly as an old `verified` is.
        #
        # The day count is asserted, not just the flag: this document is overdue
        # on either clock, so `stale is True` alone would hold even if the
        # revocation were ignored and `created` read instead (918 days over
        # rather than 553).
        self._decision(settings, "adr-0001", revoked="2024-01-01")
        dispatcher.dispatch("reindex", {})

        assert dispatcher.dispatch("get", {"doc_id": "adr-0001"})["stale"] is True
        [finding] = _stale_findings(dispatcher)
        assert "553 day(s) past its 365-day review cadence" in finding["message"]

    def test_the_finding_names_the_revocation(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # A reader who sees "never verified, created 2023-01-01" on a document
        # somebody verified last year reads the finding as a bug.
        self._decision(settings, "adr-0001", revoked="2024-01-01")
        dispatcher.dispatch("reindex", {})

        [finding] = _stale_findings(dispatcher)
        assert "verification revoked 2024-01-01" in finding["message"]

    def test_a_standing_verification_still_wins(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # Both dates present is the shape a re-verification leaves behind if
        # anything ever writes one; `verified` is the one the cadence reads.
        self._decision(settings, "adr-0001", verified="2026-07-01", revoked="2024-01-01")
        dispatcher.dispatch("reindex", {})

        assert dispatcher.dispatch("get", {"doc_id": "adr-0001"})["stale"] is False


class TestTheEvidenceOutlivesTheCalendar:
    """`verified_code` digests are kept across a revocation."""

    def test_code_changed_still_reports_after_an_edit_revoked_the_stamp(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        # The digests answer "has the code moved since somebody read this",
        # which is exactly the question a document whose calendar just reset
        # still has open. Dropping them would silence the sharper of the two
        # staleness signals on the documents most likely to need it.
        (tmp_path / ".git").mkdir()
        source = tmp_path / "src" / "auth.py"
        source.parent.mkdir()
        source.write_text("original\n", encoding="utf-8")
        settings.ensure_directories()
        container = build_container(settings, background_embeddings=False, clock=FixedClock())
        try:
            docs = container.dispatcher
            view = docs.dispatch(
                "add",
                {
                    "type": "decision",
                    "title": "Auth",
                    "description": "how auth works",
                    "code": ["src/*.py"],
                },
            )
            doc_id = view["id"]
            docs.dispatch("update", {"doc_id": doc_id, "mark_verified": True})
            source.write_text("rewritten\n", encoding="utf-8")
            docs.dispatch("update", {"doc_id": doc_id, "set_title": "Authentication"})

            assert docs.dispatch("get", {"doc_id": doc_id})["verified"] is None
            findings = [i for i in docs.dispatch("check", {}) if i["kind"] == "code-changed"]
            assert [i["doc_ids"] for i in findings] == [(doc_id,)]
            assert f"withdrawn on {TODAY.isoformat()}" in findings[0]["message"]
        finally:
            container.close()


class TestTheAuditQuery:
    def test_expr_lists_the_lapsed_verifications(self, dispatcher: Dispatcher) -> None:
        # How a corpus is asked which verifications it lost — the question the
        # reporter was answering with a side script.
        lapsed = _verified_decision(dispatcher, title="Rotation")
        dispatcher.dispatch("update", {"doc_id": lapsed, "set_title": "Key rotation"})
        standing = _verified_decision(dispatcher, title="Backups")

        rows = dispatcher.dispatch("query", {"expr": "revoked"})

        assert [row["id"] for row in rows] == [lapsed]
        assert standing not in {row["id"] for row in rows}


class TestTheVerifiedContentDigest:
    """`verification-outdated`: the stamp stands over text nobody read.

    The write path catches a CLI edit. This catches the same move made any other
    way — a hand-edit, a merge resolved into the body, or a teammate on a docir
    that predates revocation. `stale` cannot: the document's calendar was reset
    by the very stamp that is now wrong.
    """

    def _findings(self, dispatcher: Dispatcher) -> list[dict]:
        return [
            issue
            for issue in dispatcher.dispatch("check", {})
            if issue["kind"] == "verification-outdated"
        ]

    def _path(self, settings: Settings, doc_id: str) -> Path:
        return next((settings.docs_root / "decisions").glob(f"{doc_id}-*.md"))

    def test_verifying_records_the_text_it_covered(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        doc_id = _verified_decision(dispatcher)

        text = self._path(settings, doc_id).read_text()
        assert "verified_content:" in text
        assert self._findings(dispatcher) == []

    def test_a_hand_edited_body_is_reported(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        doc_id = _verified_decision(dispatcher)
        path = self._path(settings, doc_id)
        path.write_text(
            path.read_text().replace("rotated by hand", "rotated by the operator"),
            encoding="utf-8",
        )
        dispatcher.dispatch("reindex", {})

        [finding] = self._findings(dispatcher)
        assert finding["doc_ids"] == (doc_id,)
        assert "edited outside the CLI" in finding["message"]
        assert finding["severity"] == "warning"

    def test_a_hand_edited_title_is_reported(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        doc_id = _verified_decision(dispatcher)
        path = self._path(settings, doc_id)
        path.write_text(
            path.read_text().replace("title: Rotation", "title: Key rotation"), encoding="utf-8"
        )
        dispatcher.dispatch("reindex", {})

        assert [i["doc_ids"] for i in self._findings(dispatcher)] == [(doc_id,)]

    def test_a_metadata_change_is_not_reported(self, dispatcher: Dispatcher) -> None:
        # The predicate `verified < updated` would fire here, on a document
        # whose verification is entirely valid: a status is the first thing that
        # moves after somebody reviews one.
        doc_id = _verified_decision(dispatcher)
        dispatcher.dispatch("tag_add", {"key": "integrity", "description": "Corpus integrity."})

        dispatcher.dispatch("update", {"doc_id": doc_id, "status": "accepted"})
        dispatcher.dispatch("update", {"doc_id": doc_id, "set_tags": ["integrity"]})
        dispatcher.dispatch("update", {"doc_id": doc_id, "set_owner": "platform-team"})

        assert self._findings(dispatcher) == []

    def test_a_cli_edit_is_not_reported_because_it_revoked_instead(
        self, dispatcher: Dispatcher
    ) -> None:
        # One event, one finding: the write path already withdrew the claim, so
        # reporting it here as well would name the same problem twice.
        doc_id = _verified_decision(dispatcher)
        dispatcher.dispatch("update", {"doc_id": doc_id, "set_title": "Key rotation"})

        assert self._findings(dispatcher) == []

    def test_a_verification_stamped_before_the_digest_existed_is_silent(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # Absent is unknown, never unchanged — the rule every other digest in
        # the corpus follows. Without it every stamp older than this release
        # would report on the day it lands.
        decisions = settings.docs_root / "decisions"
        decisions.mkdir(parents=True, exist_ok=True)
        (decisions / "adr-0001-legacy.md").write_text(
            "---\ncreated: '2026-07-01'\ndescription: verified by an older docir\n"
            "id: adr-0001\nrelated: []\nstatus: proposed\ntags: []\ntitle: Legacy\n"
            "type: decision\nupdated: '2026-07-01'\nverified: '2026-07-01'\n---\n\nbody\n",
            encoding="utf-8",
        )
        dispatcher.dispatch("reindex", {})

        assert self._findings(dispatcher) == []

    def test_re_verifying_clears_it(self, dispatcher: Dispatcher, settings: Settings) -> None:
        doc_id = _verified_decision(dispatcher)
        path = self._path(settings, doc_id)
        path.write_text(path.read_text().replace("by hand", "by the operator"), encoding="utf-8")
        dispatcher.dispatch("reindex", {})
        assert self._findings(dispatcher)

        dispatcher.dispatch("update", {"doc_id": doc_id, "mark_verified": True})

        assert self._findings(dispatcher) == []

    def test_withdrawing_the_stamp_clears_it_too(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # The other honest answer: not "I re-read it" but "nobody did".
        doc_id = _verified_decision(dispatcher)
        path = self._path(settings, doc_id)
        path.write_text(path.read_text().replace("by hand", "by the operator"), encoding="utf-8")
        dispatcher.dispatch("reindex", {})

        dispatcher.dispatch("update", {"doc_id": doc_id, "clear_verified": True})

        assert self._findings(dispatcher) == []

    def test_it_is_a_warning_that_strict_does_not_fail_on(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # A branch that edits a document by hand is not a broken corpus, and a
        # gate that red-builds one is a gate people delete.
        doc_id = _verified_decision(dispatcher)
        path = self._path(settings, doc_id)
        path.write_text(path.read_text().replace("by hand", "by the operator"), encoding="utf-8")
        dispatcher.dispatch("reindex", {})

        assert self._findings(dispatcher)
        assert [
            i["kind"] for i in dispatcher.dispatch("check", {}) if i["severity"] == "error"
        ] == []

    def test_check_fix_leaves_it(self, dispatcher: Dispatcher, settings: Settings) -> None:
        # A repair has nothing to read *with*: clearing this means deciding the
        # document is still true, or deciding it is not.
        doc_id = _verified_decision(dispatcher)
        path = self._path(settings, doc_id)
        path.write_text(path.read_text().replace("by hand", "by the operator"), encoding="utf-8")
        dispatcher.dispatch("reindex", {})

        dispatcher.dispatch("repair", {})

        assert [i["doc_ids"] for i in self._findings(dispatcher)] == [(doc_id,)]

    def test_verifying_with_an_edit_records_the_rewritten_text(
        self, dispatcher: Dispatcher
    ) -> None:
        # The digest has to cover the document the write produces. Hashing the
        # pre-edit text would report the document as altered the instant the
        # call that verified it returned.
        doc_id = _verified_decision(dispatcher)

        dispatcher.dispatch(
            "update",
            {
                "doc_id": doc_id,
                "replace_section": ["Rotation", "The key rotates on a schedule."],
                "mark_verified": True,
            },
        )

        assert self._findings(dispatcher) == []
