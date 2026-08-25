"""`query --expr` — a question the fixed flags cannot ask (issue-9b2d2ab09060).

Two layers. The projection and the evaluator are pure and are tested as such;
the wiring is tested through the dispatcher, because what has to hold there is
that the expression is a *post-SQL* predicate applied before the limit, exactly
like `--stale` and `--code`.
"""

from __future__ import annotations

from datetime import date

import pytest

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.services.expressions import (
    EDGE_FIELDS,
    PROJECTION_FIELDS,
    compile_expression,
    matches,
    project,
)
from docir.platform.errors import ValidationError


def _doc(**over: object) -> Document:
    base: dict[str, object] = {
        "id": "adr-0001",
        "title": "T",
        "description": "D",
        "type": "decision",
        "status": "accepted",
        "created": date(2026, 1, 1),
        "updated": date(2026, 1, 2),
    }
    return Document(**{**base, **over})  # type: ignore[arg-type]


class TestProjection:
    def test_it_carries_the_document_s_own_fields(self) -> None:
        view = project(_doc(tags=("auth",), owner="platform"), stale=True)
        assert view["id"] == "adr-0001"
        assert view["tags"] == ["auth"]
        assert view["owner"] == "platform"
        assert view["stale"] is True

    def test_an_absent_owner_is_null_not_empty_string(self) -> None:
        # So `owner == null` reads as "nobody owns this" in an expression,
        # rather than needing to know docir stores it as "".
        assert project(_doc(), stale=False)["owner"] is None

    def test_dates_are_strings_an_expression_can_compare(self) -> None:
        view = project(_doc(), stale=False)
        assert view["created"] == "2026-01-01"
        assert view["verified"] is None

    def test_edges_arrive_resolved_in_both_directions(self) -> None:
        view = project(
            _doc(),
            stale=False,
            outgoing=[
                {"to": "adr-0002", "kind": "supersedes", "type": "decision", "status": "superseded"}
            ],
            incoming=[
                {"to": "issue-0003", "kind": "relates_to", "type": "issue", "status": "open"}
            ],
        )
        assert view["related"][0]["status"] == "superseded"
        assert view["related_by"][0]["type"] == "issue"


class TestEvaluation:
    def _match(self, expression: str, view: dict) -> bool:
        return matches(compile_expression(expression), view)

    def test_a_truthy_result_keeps_the_document(self) -> None:
        assert self._match("stale", project(_doc(), stale=True))

    def test_an_empty_list_is_a_miss(self) -> None:
        # The property that lets `related[?kind=='supersedes']` read as a filter
        # without a comparison bolted on.
        assert not self._match("related[?kind=='supersedes']", project(_doc(), stale=False))

    def test_a_non_empty_list_is_a_hit(self) -> None:
        view = project(
            _doc(),
            stale=False,
            outgoing=[{"to": "x", "kind": "supersedes", "type": "decision", "status": "accepted"}],
        )
        assert self._match("related[?kind=='supersedes']", view)

    def test_a_syntax_error_is_reported_before_any_document_is_read(self) -> None:
        # A syntax error is a property of the expression. Finding out on the
        # first *matching* document would make the error depend on the corpus.
        with pytest.raises(ValidationError, match="not a valid JMESPath"):
            compile_expression("this is not ((valid")

    def test_a_field_the_projection_lacks_is_refused(self) -> None:
        """The more dangerous fault, and the reason this check exists.

        An unknown identifier evaluates to `null` rather than raising, so
        `stauts == 'open'` matches nothing and reads exactly like a corpus with
        nothing wrong. A *declared* check carrying that typo would run forever
        finding nothing.
        """
        with pytest.raises(ValidationError) as exc:
            compile_expression("stauts == 'open'")
        message = str(exc.value)
        assert "'stauts'" in message
        assert "status" in message, "the error must name what would have worked"

    def test_bare_null_is_an_identifier_and_is_refused(self) -> None:
        """JMESPath spells a literal with backticks; bare `null` is a *field*.

        `owner == null` therefore compares against a key no document has, which
        is `None`, which is what the author meant — so it works by accident and
        for the wrong reason. Every example docir shipped used that form until
        this check refused it.
        """
        with pytest.raises(ValidationError, match="'null'"):
            compile_expression("owner == null")
        compile_expression("owner == `null`")

    def test_an_unknown_field_inside_an_edge_filter_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="'knd'"):
            compile_expression("related[?knd=='x']")

    def test_every_projection_key_is_accepted(self) -> None:
        # Derived from the constant, so a field added to `project` without being
        # declared fails here rather than being silently unwritable.
        for field in sorted(PROJECTION_FIELDS):
            compile_expression(f"{field} != `null`")

    def test_the_declared_fields_are_exactly_what_project_returns(self) -> None:
        """The two would otherwise drift: a new key in `project` would be
        unusable in an expression, and a stale entry here would let a typo
        through."""
        assert set(project(_doc(), stale=False)) == PROJECTION_FIELDS

    def test_edge_fields_are_exactly_what_an_edge_carries(self) -> None:
        view = project(
            _doc(),
            stale=False,
            outgoing=[{"to": "x", "kind": "relates_to", "type": "decision", "status": "accepted"}],
        )
        assert set(view["related"][0]) == EDGE_FIELDS

    def test_an_empty_expression_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="needs an expression"):
            compile_expression("   ")


class TestQueryWiring:
    def _add(self, dispatcher, title: str, **over: object) -> str:
        payload: dict[str, object] = {
            "type": "decision",
            "title": title,
            "description": title,
            **over,
        }
        return str(dispatcher.dispatch("add", payload)["id"])

    def test_it_filters_on_the_document_s_own_fields(self, dispatcher) -> None:
        self._add(dispatcher, "Owned", owner="platform")
        self._add(dispatcher, "Unowned")
        rows = dispatcher.dispatch("query", {"expr": "owner == 'platform'", "limit": 10})
        assert [r["title"] for r in rows] == ["Owned"]

    def test_it_sees_a_neighbour_s_resolved_status(self, dispatcher) -> None:
        """The question that decided the projection carries resolved edges.

        With ids alone this is unanswerable: the fact wanted belongs to the
        *target*, and an expression that could not reach it would ship a grammar
        without its motivating case.
        """
        old = self._add(dispatcher, "Old decision")
        dispatcher.dispatch("update", {"doc_id": old, "status": "accepted"})
        dispatcher.dispatch("update", {"doc_id": old, "status": "superseded"})
        new = self._add(dispatcher, "New decision", related=[f"{old}:supersedes"])
        rows = dispatcher.dispatch("query", {"expr": "related[?status=='superseded']", "limit": 10})
        assert [r["id"] for r in rows] == [new]

    def test_it_sees_incoming_edges(self, dispatcher) -> None:
        target = self._add(dispatcher, "Depended upon")
        self._add(dispatcher, "Depends", related=[f"{target}:depends_on"])
        rows = dispatcher.dispatch(
            "query", {"expr": "related_by[?kind=='depends_on']", "limit": 10}
        )
        assert [r["id"] for r in rows] == [target]

    def test_the_limit_counts_matches_not_rows_scanned(self, dispatcher) -> None:
        # The seam `--stale` and `--code` already share: `--expr ... --limit 1`
        # means one matching document, not the matches among the first one.
        for index in range(4):
            self._add(dispatcher, f"Doc {index}", owner="platform" if index == 3 else "")
        rows = dispatcher.dispatch("query", {"expr": "owner == 'platform'", "limit": 1})
        assert len(rows) == 1
        assert rows[0]["title"] == "Doc 3"

    def test_it_composes_with_the_flags_rather_than_replacing_them(self, dispatcher) -> None:
        self._add(dispatcher, "A decision", owner="platform")
        dispatcher.dispatch(
            "add", {"type": "issue", "title": "An issue", "description": "x", "owner": "platform"}
        )
        rows = dispatcher.dispatch(
            "query", {"types": ["issue"], "expr": "owner == 'platform'", "limit": 10}
        )
        assert [r["title"] for r in rows] == ["An issue"]

    def test_absent_changes_nothing(self, dispatcher) -> None:
        self._add(dispatcher, "Only one")
        assert dispatcher.dispatch("query", {"limit": 10}) == (
            dispatcher.dispatch("query", {"limit": 10, "expr": None})
        )


class TestBrokenExpressionLint:
    """`lint --deep` flags a documented `--expr` that would not run.

    Every other invocation docir checks is checked for shape — the command
    exists, the flag exists. This is the one flag whose argument is a language.
    """

    def _lint(self, body: str) -> list:
        from docir.modules.documents.domain.services.similarity_lint import SimilarityLinter

        doc = Document(
            id="arch-0001",
            title="T",
            description="D",
            type="architecture",
            status="active",
            created=date(2026, 1, 1),
            updated=date(2026, 1, 1),
            body=body,
        )
        return SimilarityLinter().find_broken_expressions([doc])

    def test_a_bare_null_literal_is_reported(self) -> None:
        found = self._lint('docir query --expr "stale && owner == null"')
        assert len(found) == 1
        assert found[0].kind == "broken-expression"
        assert "null" in found[0].message

    def test_a_mistyped_field_is_reported(self) -> None:
        assert len(self._lint("docir query --expr \"stauts == 'open'\"")) == 1

    def test_a_valid_expression_is_silent(self) -> None:
        assert self._lint("docir query --expr \"related[?kind=='supersedes']\"") == []

    def test_a_shell_escaped_backtick_is_not_a_failure(self) -> None:
        """Correct documentation must not be reported.

        A backtick inside double quotes is command substitution, so a shell
        example escapes them — the argument is unescaped before it is compiled.
        """
        assert self._lint('docir query --expr "length(tags) == \\`0\\`"') == []

    def test_prose_that_merely_looks_like_an_expression_is_ignored(self) -> None:
        # Why the net is narrow: a sweep of backticked spans over docir's own
        # corpus found 13 apparent failures and one real one, the rest being
        # quoted assertions, error messages and sentences.
        assert self._lint("The test asserts `9 == 3` and fails, since `old == new`.") == []
