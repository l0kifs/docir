"""Tier 1 structural checks — graph-level warnings, never write-blocking.

Run on demand (``docs check``) or in CI, these surface graph-shape problems as
warnings rather than failing an agent mid-task:

* cycles in the relation graph,
* orphan documents (no incoming or outgoing relations),
* layering violations — a higher-level type *depending on* a lower-level one,
* stale documents — past their type's review cadence (when a date is supplied).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.entities.relation import Relation
from docir.modules.documents.domain.schema import Schema

# DFS coloring states for cycle detection.
_WHITE, _GREY, _BLACK = 0, 1, 2

#: Relation kinds that assert a *dependency*, and so are the only ones a layering
#: violation can be read from. Everything else — `relates_to`, `supersedes`,
#: `contradicts`, `implements`, and any kind a custom schema adds — is lateral or
#: merely associative, and says nothing about which document relies on which.
#:
#: This was written the other way round, as an exemption list holding
#: `supersedes`/`contradicts`, which made *every other* kind a dependency claim.
#: The default kind for a bare id in `related:` is `relates_to`, so the most
#: natural thing a user can model — a decision linking the issue that motivated
#: it, the pairing in the README's own quickstart — produced a permanent
#: violation that no edit could silence. A warning that fires on correct usage
#: teaches people to ignore the whole of `docs check`, which is where the
#: duplicate-id detection lives.
#:
#: Consequence of the allowlist, accepted deliberately: a relation kind added by
#: a custom schema is not layering-checked until it is named here. Silence on an
#: unknown kind is the right default for a heuristic warning; noise on a correct
#: one is not.
_DEPENDENCY_KINDS = frozenset({"depends_on", "refines"})


#: Findings that mean the corpus is *broken* — a document is unreachable, or an
#: edge resolves to nothing. These are what a merge gate must stop.
ERROR_KINDS: frozenset[str] = frozenset({"duplicate-id", "dangling", "malformed"})

#: Everything else (`orphan`, `cycle`, `layering`, `stale`, `unknown-type`,
#: `unknown-status`, `unknown-tag`) describes shape or classification, not
#: damage. `orphan` in particular fires for any document with no relations — the
#: default state of a new one — so treating these as build failures made the gate
#: unusable on a healthy corpus.
#:
#: `unknown-status`/`unknown-tag` are warnings for the same reason as
#: `unknown-type`: the document is still readable and every edge still resolves,
#: the schema simply no longer recognises how it is classified. Promoting them
#: would also fail CI for any repo that already carries a hand-edited tag —
#: the exact way the `--strict` gate became unusable before. `--strict-all`
#: covers anyone who does want hand-edits to block a merge.
ERROR = "error"
WARNING = "warning"


def severity_for(kind: str) -> str:
    """Whether a finding kind blocks a merge (`error`) or informs (`warning`)."""
    return ERROR if kind in ERROR_KINDS else WARNING


@dataclass(frozen=True, slots=True)
class CheckIssue:
    """One structural finding: a kind, a message, the ids involved, a severity.

    ``severity`` is derived from ``kind`` unless given explicitly, so a new check
    cannot forget to classify itself — it just has to be added to
    :data:`ERROR_KINDS` if it means damage.
    """

    kind: str
    message: str
    doc_ids: tuple[str, ...]
    severity: str = ""

    def __post_init__(self) -> None:
        if not self.severity:
            object.__setattr__(self, "severity", severity_for(self.kind))


class GraphChecker:
    """Computes Tier 1 structural warnings over the document graph."""

    def __init__(self, schema: Schema) -> None:
        self._schema = schema

    def check(
        self,
        documents: list[Document],
        relations: list[Relation],
        today: date | None = None,
        known_tags: frozenset[str] | None = None,
    ) -> list[CheckIssue]:
        """Run every Tier 1 check over the indexed corpus.

        ``known_tags`` is the tag registry; ``None`` skips the tag check, the
        same permissive-when-absent convention the relation-kind registry uses.
        """
        issues: list[CheckIssue] = []
        issues.extend(self._find_unknown_type(documents))
        issues.extend(self._find_unknown_status(documents))
        if known_tags is not None:
            issues.extend(self._find_unknown_tag(documents, known_tags))
        issues.extend(self._find_dangling(documents, relations))
        issues.extend(self._find_cycles(relations))
        issues.extend(self._find_orphans(documents, relations))
        issues.extend(self._find_layering_violations(documents, relations))
        if today is not None:
            issues.extend(self._find_stale(documents, today))
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

    def _find_unknown_tag(
        self, documents: list[Document], known_tags: frozenset[str]
    ) -> list[CheckIssue]:
        """Flag tags that are not in the registry.

        Also unreachable through the CLI (Tier 0 rejects an unregistered tag on
        write), so it means a hand-edit or a merge. The tag still filters
        `query --tag`, but `tag list` does not know it and `tag rename` / `tag
        rm` cannot touch it — the registry has stopped describing the
        vocabulary actually in use.
        """
        issues: list[CheckIssue] = []
        for doc in documents:
            unknown = sorted(set(doc.tags) - known_tags)
            if not unknown:
                continue
            issues.append(
                CheckIssue(
                    kind="unknown-tag",
                    message=(
                        f"{doc.id!r} uses unregistered tag(s) "
                        f"{', '.join(repr(t) for t in unknown)}; "
                        "register them with `docir tag add` or remove them"
                    ),
                    doc_ids=(doc.id,),
                )
            )
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

    def _find_stale(self, documents: list[Document], today: date) -> list[CheckIssue]:
        """Flag documents past their type's review cadence (staleness as data).

        Staleness is honest human re-verification, not a heuristic: a type opts
        in with a ``review_days`` cadence, and a document resets the clock by
        being ``--verified``. Types with no cadence are never flagged.
        """
        issues: list[CheckIssue] = []
        for doc in documents:
            if doc.archived or doc.type not in self._schema.types:
                continue
            cadence = self._schema.types[doc.type].review_days
            if cadence <= 0:
                continue
            overdue_by = (today - doc.stale_reference_date()).days - cadence
            if overdue_by > 0:
                owner = f" (owner: {doc.owner})" if doc.owner else ""
                issues.append(
                    CheckIssue(
                        kind="stale",
                        message=(
                            f"{doc.id!r} is {overdue_by} day(s) past its "
                            f"{cadence}-day review cadence{owner}"
                        ),
                        doc_ids=(doc.id,),
                    )
                )
        return issues

    def _find_dangling(
        self, documents: list[Document], relations: list[Relation]
    ) -> list[CheckIssue]:
        """Flag ``related`` links whose target document does not exist.

        A merge can drop a document (deleted on one branch) while another
        branch still links to it, leaving a reference the index cannot resolve.
        """
        existing = {doc.id for doc in documents}
        issues: list[CheckIssue] = []
        seen: set[tuple[str, str]] = set()
        for rel in relations:
            if rel.target in existing or (rel.source, rel.target) in seen:
                continue
            seen.add((rel.source, rel.target))
            issues.append(
                CheckIssue(
                    kind="dangling",
                    message=(f"{rel.source!r} references missing document {rel.target!r}"),
                    doc_ids=(rel.source, rel.target),
                )
            )
        return issues

    def _find_cycles(self, relations: list[Relation]) -> list[CheckIssue]:
        adjacency: dict[str, list[str]] = {}
        for rel in relations:
            adjacency.setdefault(rel.source, []).append(rel.target)

        color: dict[str, int] = {}
        issues: list[CheckIssue] = []
        seen_cycles: set[frozenset[str]] = set()

        def visit(node: str, stack: list[str]) -> None:
            color[node] = _GREY
            stack.append(node)
            for nxt in adjacency.get(node, ()):
                state = color.get(nxt, _WHITE)
                if state == _WHITE:
                    visit(nxt, stack)
                elif state == _GREY:
                    cycle = stack[stack.index(nxt) :]
                    key = frozenset(cycle)
                    if key not in seen_cycles:
                        seen_cycles.add(key)
                        issues.append(
                            CheckIssue(
                                kind="cycle",
                                message="relation cycle: " + " -> ".join([*cycle, nxt]),
                                doc_ids=tuple(cycle),
                            )
                        )
            stack.pop()
            color[node] = _BLACK

        for node in list(adjacency):
            if color.get(node, _WHITE) == _WHITE:
                visit(node, [])
        return issues

    def _find_orphans(
        self, documents: list[Document], relations: list[Relation]
    ) -> list[CheckIssue]:
        connected: set[str] = set()
        for rel in relations:
            connected.add(rel.source)
            connected.add(rel.target)
        issues: list[CheckIssue] = []
        for doc in documents:
            if doc.archived:
                continue
            if doc.id not in connected:
                issues.append(
                    CheckIssue(
                        kind="orphan",
                        message=f"orphan document {doc.id!r} has no relations",
                        doc_ids=(doc.id,),
                    )
                )
        return issues

    def _find_layering_violations(
        self, documents: list[Document], relations: list[Relation]
    ) -> list[CheckIssue]:
        level_by_id: dict[str, int] = {}
        type_by_id: dict[str, str] = {}
        for doc in documents:
            if doc.type in self._schema.types:
                level_by_id[doc.id] = self._schema.types[doc.type].level
                type_by_id[doc.id] = doc.type
        issues: list[CheckIssue] = []
        for rel in relations:
            if rel.kind not in _DEPENDENCY_KINDS:
                continue
            src_level = level_by_id.get(rel.source)
            tgt_level = level_by_id.get(rel.target)
            if src_level is None or tgt_level is None:
                continue
            if src_level > tgt_level:
                issues.append(
                    CheckIssue(
                        kind="layering",
                        message=(
                            f"layering violation: {type_by_id[rel.source]} "
                            f"{rel.source!r} depends on lower-level "
                            f"{type_by_id[rel.target]} {rel.target!r}"
                        ),
                        doc_ids=(rel.source, rel.target),
                    )
                )
        return issues
