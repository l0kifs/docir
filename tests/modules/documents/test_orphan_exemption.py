"""`isolated:` — the reviewed exemption from the `orphan` warning.

`orphan` used to be cleared by a prose mention, which made it self-clearing: the
body most likely to name a list of orphan ids is the triage of that list, so
writing the diagnosis closed every id it diagnosed (issue-77a09761e1d4). The
distinction the triage was drawing — "correctly isolated" against "still
unwired" — is a judgement, and adr-e98749aa457d records it as a field instead.

The tests here are about the field being a *recorded* thing: it survives a round
trip through the file, it is auditable and reversible, and it does not move the
review clock on its way past.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from docir.config.settings import Settings
from docir.entry_points.composition import build_container
from docir.entry_points.dispatch import Dispatcher
from docir.platform.clock import Clock


class _AdvancingClock(Clock):
    """A clock that moves one day per read.

    The suite's `FixedClock` cannot tell "this write left `updated` alone" from
    "every write stamps the same frozen date", which is the whole question here.
    """

    def __init__(self) -> None:
        self._day = date(2026, 7, 7)

    def today(self) -> date:
        self._day += timedelta(days=1)
        return self._day


def _orphans(dispatcher: Dispatcher) -> set[str]:
    return {
        issue["doc_ids"][0]
        for issue in dispatcher.dispatch("check", {})
        if issue["kind"] == "orphan"
    }


def _add(dispatcher: Dispatcher, **extra: object) -> str:
    payload: dict[str, object] = {
        "type": "decision",
        "title": "Alone",
        "description": "d",
        "body": "x",
    }
    payload.update(extra)
    return str(dispatcher.dispatch("add", payload)["id"])


class TestItSilencesTheFinding:
    def test_an_isolated_document_is_not_reported(self, dispatcher: Dispatcher) -> None:
        doc = _add(dispatcher, isolated="scope deferred; nothing depends on it yet")
        assert doc not in _orphans(dispatcher)

    def test_the_same_document_without_it_is_reported(self, dispatcher: Dispatcher) -> None:
        # The bug-injection half: without this, the test above passes just as
        # well against a check that reports no orphans at all.
        assert _add(dispatcher) in _orphans(dispatcher)

    def test_update_exempts_and_an_empty_string_withdraws(self, dispatcher: Dispatcher) -> None:
        doc = _add(dispatcher)
        assert doc in _orphans(dispatcher)

        dispatcher.dispatch("update", {"doc_id": doc, "set_isolated": "standalone glossary"})
        assert doc not in _orphans(dispatcher)

        # Reversible, and by the documented spelling: `""` is what the CLI
        # help and the skill both tell a caller to pass.
        dispatcher.dispatch("update", {"doc_id": doc, "set_isolated": ""})
        assert doc in _orphans(dispatcher)

    def test_it_exempts_only_the_document_carrying_it(self, dispatcher: Dispatcher) -> None:
        _add(dispatcher, title="Exempt", isolated="by design")
        unwired = _add(dispatcher, title="Unwired")
        assert _orphans(dispatcher) == {unwired}, "the exemption must not travel"

    def test_it_silences_nothing_but_orphan(self, dispatcher: Dispatcher) -> None:
        # An exemption from "nobody connected this" is not an exemption from
        # "this edge points at nothing" — that one is an error and gates a merge.
        doc = _add(dispatcher, isolated="by design")
        settings_free_edit = {"doc_id": doc, "set_related": ["adr-deadbeefcafe"]}
        with pytest.raises(Exception):  # noqa: B017 - any refusal will do; the write must fail
            dispatcher.dispatch("update", settings_free_edit)


class TestItIsRecorded:
    def test_it_round_trips_through_the_file_and_a_rebuild(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # In frontmatter, not the index: the index is gitignored, so an
        # exemption that lived only there would be a judgement a teammate
        # cloning the repo could neither read nor review.
        reason = "no acceptance criterion references this flow"
        doc = _add(dispatcher, isolated=reason)
        raw = (settings.docs_root / dispatcher.dispatch("get", {"doc_id": doc})["path"]).read_text(
            encoding="utf-8"
        )
        assert f"isolated: {reason}" in raw

        dispatcher.dispatch("reindex", {})
        assert dispatcher.dispatch("get", {"doc_id": doc})["isolated"] == reason
        assert doc not in _orphans(dispatcher)

    def test_a_document_that_is_not_exempt_writes_no_key(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # The stewardship-key rule: absent rather than empty, so a corpus that
        # exempts nothing carries no new line in any file.
        doc = _add(dispatcher)
        raw = (settings.docs_root / dispatcher.dispatch("get", {"doc_id": doc})["path"]).read_text(
            encoding="utf-8"
        )
        assert "isolated" not in raw

    def test_the_reason_is_readable_without_fetching_the_body(self, dispatcher: Dispatcher) -> None:
        # `query --expr "isolated"` is the audit, and an audit that has to
        # `get` each hit to read the reason is one nobody runs. So the reason
        # rides on the skeleton.
        reason = "standalone glossary"
        doc = _add(dispatcher, isolated=reason)
        _add(dispatcher, title="Unwired")
        rows = dispatcher.dispatch("query", {"expr": "isolated", "limit": 10})
        assert [(row["id"], row["isolated"]) for row in rows] == [(doc, reason)]
        assert "body" not in rows[0]

    def test_it_stamps_updated_like_every_other_flag(self, settings: Settings) -> None:
        # `update` advances `updated` whenever it changes anything, `--set-owner`
        # and `--verified` included, and the exemption is not carved out of that:
        # the mechanical-rewrite rule governs the writes nobody asked for — a tag
        # rename, `check --fix`, a forced delete's unlink — not an edit somebody
        # typed. Pinned because the docstrings first claimed the opposite.
        #
        # On an *advancing* clock, not the suite's frozen one: with the create
        # and the edit stamped the same day, "it moved" and "it did not" are the
        # same assertion, and either claim passes.
        container = build_container(settings, background_embeddings=False, clock=_AdvancingClock())
        try:
            dispatcher = container.dispatcher
            doc = _add(dispatcher)
            created = dispatcher.dispatch("get", {"doc_id": doc})["updated"]

            exempted = dispatcher.dispatch("update", {"doc_id": doc, "set_isolated": "by design"})
            assert exempted["updated"] > created
        finally:
            container.close()

    def test_check_fix_neither_grants_nor_withdraws_it(self, dispatcher: Dispatcher) -> None:
        # `--fix` repairs only what needs no guess. Deciding that a document is
        # meant to stand alone is precisely a guess, in both directions.
        exempt = _add(dispatcher, title="Exempt", isolated="by design")
        unwired = _add(dispatcher, title="Unwired")
        dispatcher.dispatch("repair", {})
        assert dispatcher.dispatch("get", {"doc_id": exempt})["isolated"] == "by design"
        assert dispatcher.dispatch("get", {"doc_id": unwired})["isolated"] == ""
        assert _orphans(dispatcher) == {unwired}
