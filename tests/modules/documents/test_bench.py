"""``docir bench`` — the retrieval instrument, pointed at the caller's corpus.

Two layers. The scorer is pure arithmetic and is tested as such. The service is
tested through the `container` fixture with the deterministic embedder, because
what it must get right is not *which* documents rank — that is the embedder's
judgement and the benchmark's own subject — but what it does with a fixture that
has outlived the corpus it judges.
"""

from __future__ import annotations

import pytest

from docir.modules.documents.domain.services.retrieval_scoring import mean, score_task
from docir.platform.errors import ValidationError


class TestScoreTask:
    def test_a_perfect_result_scores_one_across_the_board(self) -> None:
        scored = score_task(["a", "b"], ["a", "b"])
        assert (scored.recall, scored.precision, scored.reciprocal_rank) == (1.0, 1.0, 1.0)

    def test_nothing_relevant_retrieved_scores_zero_rather_than_undefined(self) -> None:
        # 0.0 rather than an omission: a task that finds nothing has to drag the
        # mean down, not vanish from it.
        scored = score_task(["x", "y"], ["a"])
        assert (scored.recall, scored.precision, scored.reciprocal_rank) == (0.0, 0.0, 0.0)

    def test_reciprocal_rank_is_of_the_first_hit(self) -> None:
        assert score_task(["x", "x2", "a"], ["a"]).reciprocal_rank == pytest.approx(1 / 3)

    def test_recall_is_over_distinct_ids(self) -> None:
        # Injected bug: counting hits rather than distinct ones lets a fixture
        # naming one document twice score 2.0.
        assert score_task(["a", "a"], ["a", "a"]).recall == 1.0

    def test_precision_is_over_what_was_returned(self) -> None:
        assert score_task(["a", "x", "y", "z"], ["a"]).precision == pytest.approx(0.25)

    def test_an_empty_result_does_not_divide_by_zero(self) -> None:
        assert score_task([], ["a"]).precision == 0.0

    def test_a_task_judging_nothing_scores_nothing(self) -> None:
        assert score_task(["a"], []).recall == 0.0

    def test_mean_of_nothing_is_zero(self) -> None:
        assert mean([]) == 0.0


class TestBench:
    """Through the dispatcher — the seam every caller crosses."""

    def _add(self, dispatcher, title: str, description: str) -> str:
        view = dispatcher.dispatch(
            "add",
            {
                "type": "decision",
                "title": title,
                "description": description,
                "body": description,
            },
        )
        return str(view["id"])

    def _bench(self, dispatcher, tasks: list[dict], **kwargs) -> dict:
        return dispatcher.dispatch("bench", {"tasks": tasks, **kwargs})

    def test_it_scores_the_three_strategies_over_the_judged_tasks(self, dispatcher) -> None:
        doc_id = self._add(dispatcher, "Auth strategy", "How clients authenticate.")
        result = self._bench(
            dispatcher, [{"id": "T01", "task": "authenticate", "relevant": [doc_id]}]
        )
        assert [row["name"] for row in result["strategies"]] == [
            "context",
            "context --expand 0",
            "search",
        ]
        assert result["scored"] == 1
        assert all(row["tasks"] == 1 for row in result["strategies"])
        assert all(0.0 <= row["recall"] <= 1.0 for row in result["strategies"])

    def test_an_id_no_document_carries_is_named_not_dropped(self, dispatcher) -> None:
        """The one failure a benchmark must not have.

        Removing an unknown id silently shrinks recall's denominator, which
        *raises* the score — so a fixture rotting looks like retrieval improving.
        """
        doc_id = self._add(dispatcher, "Auth strategy", "How clients authenticate.")
        result = self._bench(
            dispatcher,
            [{"id": "T01", "task": "authenticate", "relevant": [doc_id, "adr-deadbeef"]}],
        )
        assert result["unresolved"] == ["adr-deadbeef"]
        assert result["dropped"] == []
        assert result["scored"] == 1

    def test_a_task_whose_ids_are_all_unknown_is_dropped_and_named(self, dispatcher) -> None:
        # Scoring it would count a certain miss against retrieval that never had
        # anything to find, and the mean would say the corpus got worse.
        self._add(dispatcher, "Auth strategy", "How clients authenticate.")
        result = self._bench(dispatcher, [{"id": "T09", "task": "x", "relevant": ["adr-gone"]}])
        assert result["dropped"] == ["T09"]
        assert result["unresolved"] == ["adr-gone"]
        assert result["scored"] == 0
        # Reported as covering nothing, rather than as a clean sweep.
        assert all(row["tasks"] == 0 and row["recall"] == 0.0 for row in result["strategies"])

    def test_unresolved_ids_are_deduped_and_sorted(self, dispatcher) -> None:
        result = self._bench(
            dispatcher,
            [
                {"id": "T01", "task": "a", "relevant": ["adr-zz", "adr-aa"]},
                {"id": "T02", "task": "b", "relevant": ["adr-zz"]},
            ],
        )
        assert result["unresolved"] == ["adr-aa", "adr-zz"]

    def test_the_limit_is_carried_into_the_report(self, dispatcher) -> None:
        # The header reads `recall@N`, so a report whose limit disagreed with the
        # run would label the wrong number.
        result = self._bench(
            dispatcher,
            [{"id": "T01", "task": "authenticate", "relevant": ["adr-x"]}],
            limit=3,
            expand=1,
        )
        assert (result["limit"], result["expand"]) == (3, 1)

    def test_a_zero_limit_is_refused_like_every_other_read(self, dispatcher) -> None:
        with pytest.raises(ValidationError):
            self._bench(dispatcher, [{"id": "T01", "task": "a", "relevant": ["adr-x"]}], limit=0)


class TestBenchDispatch:
    def test_a_fixture_entry_without_relevant_ids_is_refused(self, dispatcher) -> None:
        with pytest.raises(ValidationError) as exc:
            dispatcher.dispatch("bench", {"tasks": [{"id": "T01", "task": "hello"}]})
        assert "relevant" in str(exc.value)

    def test_a_fixture_entry_without_a_task_names_its_position(self, dispatcher) -> None:
        # The id is exactly what may be missing from a hand-written fixture, so
        # the position is what makes the error actionable.
        with pytest.raises(ValidationError) as exc:
            dispatcher.dispatch("bench", {"tasks": [{"relevant": ["adr-x"]}]})
        assert "#1" in str(exc.value)

    def test_an_empty_task_list_is_refused(self, dispatcher) -> None:
        with pytest.raises(ValidationError):
            dispatcher.dispatch("bench", {"tasks": []})

    def test_an_entry_missing_an_id_is_numbered_rather_than_rejected(self, dispatcher) -> None:
        # A fixture is hand-written; requiring an id for every row buys nothing
        # the position does not already give the reader.
        result = dispatcher.dispatch("bench", {"tasks": [{"task": "hi", "relevant": ["adr-x"]}]})
        assert result["dropped"] == ["#1"]
