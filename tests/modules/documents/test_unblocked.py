"""`unblocked` — the finding that reports good news.

A `depends_on` edge claims this work waits on that work. Until this check
existed only `context` expansion ever read it, and only when a caller happened
to query nearby, so a blocker could clear and the thing it blocked would sit
there with the graph holding the answer and nobody asking
(issue-fd086c0c6ab0 waited on a resolved issue for two commits).
"""

from __future__ import annotations

from datetime import date

import pytest

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.entities.relation import Relation
from docir.modules.documents.domain.schema import Schema
from docir.modules.documents.domain.services.graph_checks import GraphChecker, severity_for
from docir.modules.documents.infra.schema_loader import parse_schema


@pytest.fixture
def schema() -> Schema:
    return parse_schema({"profiles": ["software"]})


def _doc(doc_id: str, status: str = "open", *, archived: bool = False) -> Document:
    return Document(
        id=doc_id,
        title=doc_id,
        description="d",
        type="issue",
        status=status,
        created=date(2026, 1, 1),
        updated=date(2026, 1, 1),
        archived=archived,
    )


def _kinds(issues) -> list[str]:
    return [i.kind for i in issues]


def _unblocked(checker: GraphChecker, docs, rels):
    return [i for i in checker.check(docs, rels) if i.kind == "unblocked"]


class TestUnblocked:
    def test_it_is_a_warning_not_an_error(self) -> None:
        # Nothing is broken. It is a scheduling fact, like `stale`.
        assert severity_for("unblocked") == "warning"

    def test_fires_when_every_dependency_has_closed(self, schema: Schema) -> None:
        docs = [_doc("issue-a"), _doc("issue-b", "resolved")]
        rels = [Relation(source="issue-a", target="issue-b", kind="depends_on")]
        found = _unblocked(GraphChecker(schema), docs, rels)
        assert len(found) == 1
        assert found[0].doc_ids == ("issue-a", "issue-b")
        assert "ready to start" in found[0].message

    def test_silent_while_any_dependency_is_still_open(self, schema: Schema) -> None:
        # Injected bug: an `any()` here instead of `all()` would announce a
        # document as ready while it is still waiting on something.
        docs = [_doc("issue-a"), _doc("issue-b", "resolved"), _doc("issue-c")]
        rels = [
            Relation(source="issue-a", target="issue-b", kind="depends_on"),
            Relation(source="issue-a", target="issue-c", kind="depends_on"),
        ]
        assert _unblocked(GraphChecker(schema), docs, rels) == []

    def test_a_document_with_no_dependencies_is_not_unblocked(self, schema: Schema) -> None:
        # It is unconstrained, not ready — and reporting it would fire on most
        # of a corpus, which is how `orphan` made `--strict` unusable.
        assert _unblocked(GraphChecker(schema), [_doc("issue-a")], []) == []

    def test_an_archived_dependency_counts_as_closed(self, schema: Schema) -> None:
        docs = [_doc("issue-a"), _doc("issue-b", archived=True)]
        rels = [Relation(source="issue-a", target="issue-b", kind="depends_on")]
        assert len(_unblocked(GraphChecker(schema), docs, rels)) == 1

    def test_a_closed_document_is_not_reported(self, schema: Schema) -> None:
        # Nobody needs telling that finished work could start.
        docs = [_doc("issue-a", "resolved"), _doc("issue-b", "resolved")]
        rels = [Relation(source="issue-a", target="issue-b", kind="depends_on")]
        assert _unblocked(GraphChecker(schema), docs, rels) == []

    def test_a_dangling_dependency_is_not_a_green_light(self, schema: Schema) -> None:
        """Treating a target nothing carries as "closed" would turn a broken
        edge into permission to start. That edge is `dangling`, and it is
        reported there."""
        docs = [_doc("issue-a")]
        rels = [Relation(source="issue-a", target="issue-gone", kind="depends_on")]
        issues = GraphChecker(schema).check(docs, rels)
        assert "unblocked" not in _kinds(issues)
        assert "dangling" in _kinds(issues)

    def test_one_dangling_dependency_suppresses_the_whole_finding(self, schema: Schema) -> None:
        """The bug an injected fault found.

        Filtering unresolvable targets out before counting looked defensive and
        was the opposite: this document arrived with one satisfied blocker and
        was announced ready, while the edge that would have said otherwise had
        been dropped on the way in.
        """
        docs = [_doc("issue-a"), _doc("issue-b", "resolved")]
        rels = [
            Relation(source="issue-a", target="issue-b", kind="depends_on"),
            Relation(source="issue-a", target="issue-gone", kind="depends_on"),
        ]
        assert _unblocked(GraphChecker(schema), docs, rels) == []

    def test_a_plain_relation_does_not_block_anything(self, schema: Schema) -> None:
        # `relates_to` asserts no reliance, so a resolved neighbour says nothing
        # about readiness. Which kinds count is the schema's `dependency`
        # property, not a hardcoded name (adr-234b956a48d8).
        docs = [_doc("issue-a"), _doc("issue-b", "resolved")]
        rels = [Relation(source="issue-a", target="issue-b", kind="relates_to")]
        assert _unblocked(GraphChecker(schema), docs, rels) == []

    def test_a_custom_blocking_kind_counts(self) -> None:
        schema = parse_schema(
            {"profiles": ["software"], "relation_types": {"blocked_by": {"blocking": True}}}
        )
        docs = [_doc("issue-a"), _doc("issue-b", "resolved")]
        rels = [Relation(source="issue-a", target="issue-b", kind="blocked_by")]
        assert len(_unblocked(GraphChecker(schema), docs, rels)) == 1

    def test_refines_is_a_dependency_and_not_a_blocker(self, schema: Schema) -> None:
        """The bug this property was split to fix.

        `refines` says the source narrows the target — structural, about where
        two documents sit relative to each other. It says nothing about
        waiting. Reading one property for both questions announced a decision
        refining a *superseded* one as ready to start, which is a problem
        reported as good news (adr-716c2eeb4e51).
        """
        docs = [_doc("adr-a"), _doc("adr-b", "resolved")]
        rels = [Relation(source="adr-a", target="adr-b", kind="refines")]
        assert _unblocked(GraphChecker(schema), docs, rels) == []
        # And the layering check still reads it, so the split lost nothing.
        assert schema.is_dependency_relation("refines")
        assert not schema.is_blocking_relation("refines")

    def test_depends_on_is_both(self, schema: Schema) -> None:
        assert schema.is_dependency_relation("depends_on")
        assert schema.is_blocking_relation("depends_on")

    def test_a_custom_dependency_alone_does_not_unblock(self) -> None:
        # Injected bug: reading `dependency` here is what shipped first.
        schema = parse_schema(
            {"profiles": ["software"], "relation_types": {"narrows": {"dependency": True}}}
        )
        docs = [_doc("issue-a"), _doc("issue-b", "resolved")]
        rels = [Relation(source="issue-a", target="issue-b", kind="narrows")]
        assert _unblocked(GraphChecker(schema), docs, rels) == []
