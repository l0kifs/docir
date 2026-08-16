"""What the schema in the file costs the corpus, measured without the index.

``docir schema validate`` used to answer one question — does this file load? —
and answer it in isolation. So the command a person runs *immediately after
editing the schema* reported ``valid: true`` while every document of a type they
had just removed fell out of the type system, silently, until someone happened
to run ``docir check`` (issue-3678c897295f).

Two properties make this a separate path rather than a call into
``MaintenanceService``:

**It reads the files, not the index.** A schema edit is a hand edit, and a hand
edit is exactly when the index is behind — a fresh clone has none at all, since
it is gitignored. Measuring the index there would report a corpus that is not
the one on disk, or nothing.

**It opens no database.** ``schema validate`` deliberately bypasses the
container, because building one loads the schema and a file too broken to start
the store would make the command meant to diagnose it unreachable. Adding an
engine here would give that property away.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.entities.relation import Relation
from docir.modules.documents.domain.schema import Schema
from docir.modules.documents.domain.services.graph_checks import CheckIssue, GraphChecker
from docir.platform.filesystem.ports import DocumentFileStore

#: Ids listed per finding kind. The full count rides alongside, so a truncated
#: list never reads as the whole story — a bound that does not say what it
#: dropped is how "covered everything" gets reported by something that did not.
SAMPLE_SIZE = 5


@dataclass(frozen=True, slots=True)
class ConformanceFinding:
    """One kind of schema mismatch, with how many documents it covers."""

    kind: str
    severity: str
    count: int
    #: Up to :data:`SAMPLE_SIZE` document ids, enough to go and look at one.
    sample: tuple[str, ...] = ()
    #: One finding's message verbatim, so the report says what is wrong and not
    #: only that something is.
    example: str = ""


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    """The corpus measured against a schema."""

    #: Documents read. Reported even when nothing is wrong, because "0 findings"
    #: over a corpus that failed to load is indistinguishable from a clean one.
    documents: int = 0
    #: Files under the docs root that do not parse, so were not measured at all.
    #: The same admission ``reindex`` makes with ``documents_skipped``: a scan
    #: that quietly dropped a document looks exactly like one that did not.
    unreadable: int = 0
    #: Distinct documents carrying at least one finding — **not** the number of
    #: findings. Tightening a type produces several per document (a status it no
    #: longer declares *and* a field it now requires), and summing those printed
    #: "14 of 8 documents", which is not a sentence about anything.
    affected: int = 0
    findings: tuple[ConformanceFinding, ...] = field(default_factory=tuple)


def check_schema_conformance(schema: Schema, file_store: DocumentFileStore) -> ConformanceReport:
    """Measure the documents on disk against ``schema``.

    Returns counts rather than every finding: the caller is a person who just
    edited a file and wants to know the size of what they did. ``docir check``
    remains the place to enumerate them.
    """
    documents = list(file_store.scan())
    issues = GraphChecker(schema).check_schema_conformance(documents, _edges(documents))
    return ConformanceReport(
        documents=len(documents),
        unreadable=len(file_store.find_malformed()),
        affected=len({issue.doc_ids[0] for issue in issues if issue.doc_ids}),
        findings=_summarize(issues),
    )


def _edges(documents: list[Document]) -> list[Relation]:
    """The relation graph as the files declare it, not as the index stored it.

    The index is the usual source, and it is the wrong one here for the reason
    the whole module reads files: after a hand edit it is behind, and this runs
    at exactly that moment.
    """
    return [
        Relation(source=document.id, target=ref.target, kind=ref.kind)
        for document in documents
        for ref in document.related
    ]


def _summarize(issues: list[CheckIssue]) -> tuple[ConformanceFinding, ...]:
    """Group findings by kind, keeping a bounded sample and one message."""
    grouped: dict[str, list[CheckIssue]] = {}
    for issue in issues:
        grouped.setdefault(issue.kind, []).append(issue)
    return tuple(
        ConformanceFinding(
            kind=kind,
            severity=found[0].severity,
            count=len(found),
            # The first id of each finding: its subject. An edge finding names
            # both ends, and the source is the document to go and look at.
            sample=tuple(issue.doc_ids[0] for issue in found[:SAMPLE_SIZE] if issue.doc_ids),
            example=found[0].message,
        )
        for kind, found in sorted(grouped.items())
    )
