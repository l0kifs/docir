"""The findings that measure documents against the **schema** alone.

Exactly these four and no others, because these are the four a *schema* edit
can cause. ``unknown-tag`` measures the tag registry — a different file that no
schema change moves — and lives in :mod:`.tag_rules`.

The grouping is load-bearing rather than tidy: ``docir schema validate`` needs
these and none of the rest, because ``orphan`` fires for every document with no
relations and would bury the answer in the default state of a healthy corpus.
A class boundary says so now, where a docstring used to.
"""

from __future__ import annotations

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.entities.relation import Relation
from docir.modules.documents.domain.schema import Schema
from docir.modules.documents.domain.services.checks.findings import CheckIssue
from docir.modules.documents.domain.services.validation import is_absent


class SchemaConformanceChecks:
    """The four findings a schema edit can cause."""

    def __init__(self, schema: Schema) -> None:
        self._schema = schema

    def run(self, documents: list[Document], relations: list[Relation]) -> list[CheckIssue]:
        """Every schema-conformance finding, in the order ``check`` reports them."""
        issues: list[CheckIssue] = []
        issues.extend(self._find_unknown_type(documents))
        issues.extend(self._find_unknown_status(documents))
        issues.extend(self._find_missing_required(documents))
        issues.extend(self._find_unknown_relation_kind(relations))
        return issues

    def _find_unknown_type(self, documents: list[Document]) -> list[CheckIssue]:
        """Flag documents whose ``type`` is not in the active schema.

        This is what disabling a profile (or a foreign file) leaves behind: a
        document of a type the current schema no longer knows. The layering and
        staleness checks silently skip such docs, so surface them explicitly —
        the ``type`` grammar can no longer be enforced on them.
        """
        issues: list[CheckIssue] = []
        for doc in documents:
            if doc.type not in self._schema.types:
                known = ", ".join(sorted(self._schema.types)) or "<none>"
                issues.append(
                    CheckIssue(
                        kind="unknown-type",
                        message=(
                            f"{doc.id!r} has unknown type {doc.type!r} not in the "
                            f"active schema; known types: {known}"
                        ),
                        doc_ids=(doc.id,),
                    )
                )
        return issues

    def _find_unknown_status(self, documents: list[Document]) -> list[CheckIssue]:
        """Flag documents whose ``status`` is not declared by their type.

        The CLI cannot produce this — Tier 0 validates every status it writes —
        so it means the frontmatter was edited by hand or merged from a branch
        with a different schema. The document is still readable, but it sits
        outside its type's state machine: no transition leads out of a status
        the grammar does not know, so `docir update --status` can never move it
        again without `--override`.
        """
        issues: list[CheckIssue] = []
        for doc in documents:
            type_schema = self._schema.types.get(doc.type)
            if type_schema is None:
                continue  # already reported as unknown-type
            if doc.status in type_schema.statuses:
                continue
            known = ", ".join(type_schema.statuses)
            issues.append(
                CheckIssue(
                    kind="unknown-status",
                    message=(
                        f"{doc.id!r} has status {doc.status!r}, which type "
                        f"{doc.type!r} does not declare; declared: {known}"
                    ),
                    doc_ids=(doc.id,),
                )
            )
        return issues

    def _find_missing_required(self, documents: list[Document]) -> list[CheckIssue]:
        """Flag documents missing a field their type declares as ``required``.

        Unlike its neighbours this does not need a hand-edit to occur: the
        schema can start requiring a field that documents written before it
        never carried. Core and profile types are compiled into the package and
        re-merged on every command, so that change arrives on *upgrade*, with no
        local edit and nothing in `git diff` to review (issue-8f6576cd7bc9).

        Until this existed the corpus was silently non-conforming and the first
        report was a write being refused — `docir update --set-title` failing on
        a field the caller was not touching, one document at a time. The finding
        answers the question that had no answer: which documents does the new
        rule break, before anyone runs into them.

        Type-declared fields only. :data:`CORE_REQUIRED_FIELDS` are the ones a
        document cannot parse without, so an absent one is already `malformed`
        and reporting it twice would only make the healthy case noisier.

        Archived documents are included, matching `unknown-status` rather than
        `unmatched-code`: this reports a rule the document does not satisfy, and
        unarchiving is a write like any other, so the finding has to survive
        being archived.
        """
        issues: list[CheckIssue] = []
        for doc in documents:
            type_schema = self._schema.types.get(doc.type)
            if type_schema is None:
                continue  # already reported as unknown-type
            missing = [
                name for name in type_schema.required_fields if is_absent(getattr(doc, name, None))
            ]
            if not missing:
                continue
            joined = ", ".join(repr(name) for name in missing)
            issues.append(
                CheckIssue(
                    kind="missing-required",
                    message=(
                        f"{doc.id!r} is missing {joined}, which type {doc.type!r} "
                        f"requires; the next write to it will be refused until "
                        f"`docir update {doc.id}` supplies it"
                    ),
                    doc_ids=(doc.id,),
                )
            )
        return issues

    def _find_unknown_relation_kind(self, relations: list[Relation]) -> list[CheckIssue]:
        """Flag edges whose ``kind`` the relation registry no longer knows.

        The third member of the hand-edit family, and the one that was missing:
        `check` reported a tag the registry does not know and a status the type
        does not declare, while an edge carrying an unregistered kind was served
        by `get`, traversed by `context`, and flagged by nothing — only
        *rewriting* it was refused, by Tier 0 (issue-0e3d1d9c81d3).

        Nothing about the edge misbehaves, which is why this is a warning and
        why it is worth reporting anyway. :meth:`Schema.relation_kind` falls
        back to :data:`CORE_RELATION_KINDS`, so a dropped `depends_on` is still
        cycle-checked and still read as a dependency by the layering check. What
        is lost is the report: the registry has stopped describing the corpus.

        A schema that registers *nothing* is permissive by construction —
        `is_known_relation_kind` answers true for every kind — so a corpus that
        predates typed edges reports nothing here, exactly as it should.

        One finding per distinct ``(source, target, kind)``: the edge is the
        thing that is misclassified, and a document is free to have one bad edge
        and five good ones.
        """
        issues: list[CheckIssue] = []
        seen: set[tuple[str, str, str]] = set()
        for rel in relations:
            edge = (rel.source, rel.target, rel.kind)
            if self._schema.is_known_relation_kind(rel.kind) or edge in seen:
                continue
            seen.add(edge)
            known = ", ".join(sorted(self._schema.relation_types))
            issues.append(
                CheckIssue(
                    kind="unknown-relation-kind",
                    message=(
                        f"{rel.source!r} links {rel.target!r} with kind {rel.kind!r}, "
                        f"which the schema does not register; registered: {known}"
                    ),
                    doc_ids=(rel.source, rel.target),
                )
            )
        return issues
