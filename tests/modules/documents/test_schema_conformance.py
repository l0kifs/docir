"""What a schema costs the corpus, reported by `docir schema validate`.

`validate` answered "does this file parse?" and nothing else, so the command a
person runs immediately after editing the schema said `valid: true` while a
corpus fell out of the type system (issue-3678c897295f). These tests pin the
report and the two properties that make it usable at that moment: it reads the
*files*, and it opens no database.
"""

from __future__ import annotations

from datetime import date

from docir.modules.documents.api import check_schema_conformance
from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.value_objects.relations import RelatedRef
from docir.modules.documents.infra.schema_loader import parse_schema
from docir.platform.filesystem.markdown_store import MarkdownDocumentFileStore

#: `decision` renamed away, its prefix claimed by the replacement -- the
#: migration adr-f8cce745d0d5 describes, measured mid-flight.
RENAMED = {
    "profiles": ["software"],
    "disable_types": ["decision"],
    "types": {
        "product_decision": {
            "prefix": "adr",
            "default_status": "draft",
            "statuses": {"draft": ["active"], "active": []},
        }
    },
}

#: `decision` kept but tightened: `owner` now required and `proposed` gone.
TIGHTENED = {
    "profiles": ["software"],
    "types": {
        "decision": {
            "prefix": "adr",
            "required": ["owner"],
            "default_status": "draft",
            "statuses": {"draft": ["active"], "active": []},
        }
    },
}


def _doc(**kw: object) -> Document:
    defaults: dict[str, object] = {
        "id": "adr-0001",
        "title": "Use Postgres",
        "description": "Why the store is Postgres.",
        "type": "decision",
        "status": "proposed",
        "created": date(2026, 1, 1),
        "updated": date(2026, 1, 2),
        "body": "A body.",
    }
    defaults.update(kw)
    return Document(**defaults)  # type: ignore[arg-type]


def _store(tmp_path, *documents: Document) -> MarkdownDocumentFileStore:
    store = MarkdownDocumentFileStore(tmp_path)
    for document in documents:
        store.write(document)
    return store


class TestWhatItReports:
    def test_a_conforming_corpus_reports_nothing(self, tmp_path) -> None:
        store = _store(tmp_path, _doc(), _doc(id="adr-0002", title="Second"))
        report = check_schema_conformance(parse_schema({"profiles": ["software"]}), store)
        assert report.documents == 2
        assert report.findings == ()
        assert report.affected == 0

    def test_a_disabled_type_strands_its_documents(self, tmp_path) -> None:
        store = _store(tmp_path, *(_doc(id=f"adr-000{n}", title=f"D{n}") for n in range(1, 4)))
        report = check_schema_conformance(parse_schema(RENAMED), store)
        assert [(f.kind, f.count) for f in report.findings] == [("unknown-type", 3)]
        assert report.affected == 3
        assert report.documents == 3

    def test_a_tightened_type_reports_each_rule_separately(self, tmp_path) -> None:
        store = _store(tmp_path, _doc())
        report = check_schema_conformance(parse_schema(TIGHTENED), store)
        assert {f.kind for f in report.findings} == {"missing-required", "unknown-status"}

    def test_affected_counts_documents_not_findings(self, tmp_path) -> None:
        # One document, two rules broken. Summing the per-kind counts printed
        # "14 of 8 document(s)", which is not a sentence about anything.
        store = _store(tmp_path, _doc())
        report = check_schema_conformance(parse_schema(TIGHTENED), store)
        assert sum(f.count for f in report.findings) == 2
        assert report.affected == 1
        assert report.affected <= report.documents

    def test_an_unknown_relation_kind_is_reported(self, tmp_path) -> None:
        store = _store(
            tmp_path,
            _doc(related=(RelatedRef("adr-0002", "invented"),)),
            _doc(id="adr-0002", title="Second"),
        )
        report = check_schema_conformance(parse_schema({"profiles": ["software"]}), store)
        assert [f.kind for f in report.findings] == ["unknown-relation-kind"]
        # Keyed on the source: that is the document to go and edit.
        assert report.findings[0].sample == ("adr-0001",)

    def test_the_sample_is_bounded_and_the_count_is_not(self, tmp_path) -> None:
        # A bound that does not say what it dropped reads as the whole story.
        store = _store(tmp_path, *(_doc(id=f"adr-{n:04d}", title=f"D{n}") for n in range(1, 13)))
        report = check_schema_conformance(parse_schema(RENAMED), store)
        finding = report.findings[0]
        assert finding.count == 12
        assert len(finding.sample) == 5

    def test_a_finding_carries_one_real_message(self, tmp_path) -> None:
        store = _store(tmp_path, _doc())
        report = check_schema_conformance(parse_schema(RENAMED), store)
        assert "adr-0001" in report.findings[0].example


class TestWhatItReads:
    def test_unparseable_files_are_counted_not_ignored(self, tmp_path) -> None:
        # A scan that quietly dropped a document looks exactly like one that did
        # not -- the same admission `reindex` makes with `documents_skipped`.
        store = _store(tmp_path, _doc())
        (tmp_path / "decisions" / "adr-9999-broken.md").write_text(
            "---\nid: adr-9999\ncreated: not-a-date\n---\n", encoding="utf-8"
        )
        report = check_schema_conformance(parse_schema({"profiles": ["software"]}), store)
        assert report.documents == 1
        assert report.unreadable == 1

    def test_an_empty_store_is_not_an_error(self, tmp_path) -> None:
        store = MarkdownDocumentFileStore(tmp_path / "nothing-here")
        report = check_schema_conformance(parse_schema({"profiles": ["software"]}), store)
        assert report.documents == 0
        assert report.findings == ()

    def test_edges_come_from_the_files_not_an_index(self, tmp_path) -> None:
        # There is no index in this test at all. A schema edit is a hand edit,
        # and a hand edit is exactly when the index is behind -- a fresh clone
        # has none, since it is gitignored.
        store = _store(
            tmp_path,
            _doc(related=(RelatedRef("adr-0002", "invented"),)),
            _doc(id="adr-0002", title="Second"),
        )
        report = check_schema_conformance(parse_schema({"profiles": ["software"]}), store)
        assert report.findings[0].kind == "unknown-relation-kind"


class TestItAgreesWithCheck:
    def test_the_same_rules_back_both_reports(self, tmp_path) -> None:
        """`check` must not call a document conforming that `validate` refuses.

        Both run `GraphChecker.check_schema_conformance`; this asserts the kinds
        line up rather than trusting that they do, because two lists of check
        names drifting apart is precisely the failure the extraction prevents.
        """
        from docir.modules.documents.domain.services.graph_checks import GraphChecker

        documents = [_doc(), _doc(id="adr-0002", title="Second")]
        schema = parse_schema(TIGHTENED)
        checker = GraphChecker(schema)

        subset = {issue.kind for issue in checker.check_schema_conformance(documents, [])}
        full = {issue.kind for issue in checker.check(documents, [])}
        assert subset <= full

        store = _store(tmp_path, *documents)
        report = check_schema_conformance(schema, store)
        assert {finding.kind for finding in report.findings} == subset
