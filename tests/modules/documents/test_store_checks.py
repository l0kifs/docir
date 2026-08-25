"""Rules a *store* states about its own corpus (issue-9b2d2ab09060, second half).

docir ships none of these. The grammar is docir's; every rule written in it is
the store's, which is the line adr-b2cfed9d5888 drew — it refused docir having
opinions about your architecture, not your ability to state yours.
"""

from __future__ import annotations

from datetime import date

import pytest

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.entities.relation import Relation
from docir.modules.documents.domain.services.graph_checks import (
    ERROR_KINDS,
    RESERVED_FINDING_KINDS,
    GraphChecker,
)
from docir.modules.documents.infra.schema_loader import parse_schema
from docir.platform.errors import SchemaError

RULE = "length(related_by[?kind=='supersedes']) > `0` && status != 'superseded'"


def _schema(**checks: dict) -> object:
    return parse_schema({"profiles": ["software"], "checks": checks})


def _doc(doc_id: str, status: str = "accepted") -> Document:
    return Document(
        id=doc_id,
        title=doc_id,
        description="d",
        type="decision",
        status=status,
        created=date(2026, 1, 1),
        updated=date(2026, 1, 1),
    )


class TestDeclaredChecks:
    def test_a_declared_rule_produces_a_finding_under_its_own_name(self) -> None:
        schema = _schema(**{"superseded-still-live": {"expr": RULE, "message": "still live"}})
        docs = [_doc("adr-old"), _doc("adr-new")]
        rels = [Relation(source="adr-new", target="adr-old", kind="supersedes")]
        found = [
            i for i in GraphChecker(schema).check(docs, rels) if i.kind == "superseded-still-live"
        ]
        assert [i.doc_ids for i in found] == [("adr-old",)]
        assert "still live" in found[0].message

    def test_it_is_a_warning_whatever_the_rule_says(self) -> None:
        """`--strict` gates on ERROR_KINDS, which means "broken" in *docir's*
        terms. A store's rule joining it would make `--strict` mean something
        different in every repository; `--strict-all` is what covers wanting
        them fatal."""
        schema = _schema(**{"my-rule": {"expr": "status == 'accepted'", "message": "m"}})
        found = [i for i in GraphChecker(schema).check([_doc("adr-a")], []) if i.kind == "my-rule"]
        assert found and all(i.severity == "warning" for i in found)
        assert "my-rule" not in ERROR_KINDS

    def test_the_satisfied_corpus_is_silent(self) -> None:
        schema = _schema(**{"superseded-still-live": {"expr": RULE, "message": "m"}})
        docs = [_doc("adr-old", "superseded"), _doc("adr-new")]
        rels = [Relation(source="adr-new", target="adr-old", kind="supersedes")]
        issues = GraphChecker(schema).check(docs, rels)
        assert not [i for i in issues if i.kind == "superseded-still-live"]

    def test_a_store_with_no_checks_gains_no_findings(self) -> None:
        before = GraphChecker(parse_schema({"profiles": ["software"]})).check([_doc("adr-a")], [])
        assert all(i.kind in RESERVED_FINDING_KINDS for i in before)


class TestLoaderValidation:
    def test_a_name_colliding_with_a_docir_finding_is_refused(self) -> None:
        """The load-bearing rule. A check called `dangling` would make
        `--strict`'s behaviour depend on whose schema is loaded."""
        with pytest.raises(SchemaError, match="collides"):
            _schema(dangling={"expr": "status == 'x'", "message": "m"})

    @pytest.mark.parametrize("kind", sorted(ERROR_KINDS))
    def test_every_error_kind_is_reserved(self, kind: str) -> None:
        # Injected bug: reserving only the warnings would let a store redefine
        # exactly the findings that gate a merge.
        assert kind in RESERVED_FINDING_KINDS

    def test_an_expression_that_does_not_compile_fails_at_load(self) -> None:
        # Not on the first document that reaches it: a syntax error is a
        # property of the schema, and the author is looking at the file now.
        with pytest.raises(SchemaError, match="JMESPath"):
            _schema(mine={"expr": "this is not ((valid", "message": "m"})

    def test_a_check_without_a_message_is_refused(self) -> None:
        """A finding with no message is a kind and an id, which tells a reader
        that something is wrong and nothing about what."""
        with pytest.raises(SchemaError, match="message"):
            _schema(mine={"expr": "status == 'x'"})

    def test_a_check_without_an_expression_is_refused(self) -> None:
        with pytest.raises(SchemaError, match="expr"):
            _schema(mine={"message": "m"})

    def test_checks_absent_is_not_an_error(self) -> None:
        assert parse_schema({"profiles": ["software"]}).checks == ()
