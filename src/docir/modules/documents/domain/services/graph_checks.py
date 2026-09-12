"""Tier 1 structural checks — graph-level warnings, never write-blocking.

Run on demand (``docir check``) or in CI, these surface graph-shape problems as
warnings rather than failing an agent mid-task:

* cycles in the relation graph,
* orphan documents (no incoming or outgoing relations),
* layering violations — a higher-level type *depending on* a lower-level one,
* unblocked documents — every dependency they declared is now closed,
* stale documents — past their type's review cadence (when a date is supplied).

This module is the **registry**. The rules themselves live in
:mod:`docir.modules.documents.domain.services.checks`, one module per cause — a
schema edit, a ``tags.yaml`` edit, the review clock and the code tree, the
authored relation graph — so that adding a staleness rule no longer opens the
file holding the cycle detector.

The finding vocabulary (:class:`CheckIssue`, :func:`severity_for`,
:data:`ERROR_KINDS`, :data:`RESERVED_FINDING_KINDS`) is re-exported here, which
is where every caller already imports it from.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.entities.relation import Relation
from docir.modules.documents.domain.schema import Schema
from docir.modules.documents.domain.services.checks.findings import (
    ERROR,
    ERROR_KINDS,
    RESERVED_FINDING_KINDS,
    WARNING,
    CheckIssue,
    severity_for,
)
from docir.modules.documents.domain.services.checks.graph_rules import GraphShapeChecks
from docir.modules.documents.domain.services.checks.schema_rules import SchemaConformanceChecks
from docir.modules.documents.domain.services.checks.tag_rules import TagRegistryChecks
from docir.modules.documents.domain.services.checks.verification_rules import VerificationChecks

__all__ = [
    "ERROR",
    "ERROR_KINDS",
    "RESERVED_FINDING_KINDS",
    "WARNING",
    "CheckIssue",
    "GraphChecker",
    "severity_for",
]


class GraphChecker:
    """Computes Tier 1 structural warnings over the document graph.

    Holds the four rule groups and the order their findings are reported in,
    and nothing else — a check belongs to the group its cause names.
    """

    def __init__(self, schema: Schema) -> None:
        self._schema_rules = SchemaConformanceChecks(schema)
        self._tag_rules = TagRegistryChecks(schema)
        self._graph_rules = GraphShapeChecks(schema)
        self._verification_rules = VerificationChecks(schema)

    def check(
        self,
        documents: list[Document],
        relations: list[Relation],
        today: date | None = None,
        known_tags: frozenset[str] | None = None,
        code_matches: Mapping[str, bool] | None = None,
        code_digests: Mapping[str, str] | None = None,
    ) -> list[CheckIssue]:
        """Run every Tier 1 check over the indexed corpus.

        ``known_tags`` is the tag registry; ``None`` skips the tag check, the
        same permissive-when-absent convention the relation-kind registry uses.
        ``code_matches`` says which ``code`` globs still name something on disk
        and is ``None`` when there is no repository to ask — a global store
        would otherwise report every pattern in it as missing. ``code_digests``
        is the same shape for the *content* of what they match, and is compared
        against what each document recorded when it was last verified.

        No check here reads the derived mention graph. ``orphan`` was the one
        that did, and issue-77a09761e1d4 took it away: a Tier 1 finding must
        not be cleared by prose, least of all by the prose that triages it.
        Mentions remain what they were built for — `context` expansion, the
        neighbour lists on `get`, and the Tier 2 `unresolved-mention` advisory.
        """
        issues: list[CheckIssue] = []
        issues.extend(self.check_schema_conformance(documents, relations))
        if known_tags is not None:
            issues.extend(self._tag_rules.run(documents, known_tags))
        issues.extend(self._graph_rules.run(documents, relations))
        issues.extend(self._verification_rules.run(documents, today, code_matches, code_digests))
        return issues

    def check_schema_conformance(
        self, documents: list[Document], relations: list[Relation]
    ) -> list[CheckIssue]:
        """The findings that measure documents against the **schema** alone.

        Split out of :meth:`check` because a second caller needs exactly these
        and none of the rest: ``docir schema validate`` reports what the schema
        in the file costs the corpus, at the moment someone edits it. The graph
        findings are irrelevant there — ``orphan`` fires for every document with
        no relations, so including them would bury the answer in the default
        state of a healthy corpus.

        ``check`` calls this rather than repeating the list, so the two cannot
        answer differently about the same document. That is the same rule
        ``is_absent`` follows across Tier 0 and Tier 1: a corpus reported as
        conforming by one and refused by the other is the worst outcome
        available.

        These four and no others because these are the four a *schema* edit can
        cause. ``unknown-tag`` measures the tag registry, which is a different
        file that no schema change moves.
        """
        return self._schema_rules.run(documents, relations)
