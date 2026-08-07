"""Tier 1 structural checks — graph-level warnings, never write-blocking.

Run on demand (``docs check``) or in CI, these surface graph-shape problems as
warnings rather than failing an agent mid-task:

* cycles in the relation graph,
* orphan documents (no incoming or outgoing relations),
* layering violations — a higher-level type *depending on* a lower-level one,
* stale documents — past their type's review cadence (when a date is supplied).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.entities.relation import Relation
from docir.modules.documents.domain.schema import Schema
from docir.modules.documents.domain.services.validation import is_absent
from docir.platform.naming import TAG_KEY_RULE, is_valid_tag_key

# DFS coloring states for cycle detection.
_WHITE, _GREY, _BLACK = 0, 1, 2

#: Relation-kind *meaning* used to live here, as two hardcoded frozensets: one
#: for "asserts a dependency" (layering) and one for "asserts a direction"
#: (cycles). Both are now properties on the schema
#: (:class:`~docir.modules.documents.domain.schema.RelationKindSchema`), because
#: a kind a custom schema adds could never join either set and so was silently
#: exempt from both checks — see the ADR for typed relation semantics.
#:
#: The history is worth keeping because both sets were wrong the same way first.
#: Each began as an *exemption* list, which made every other kind — including
#: `relates_to`, what a bare id in `related:` means — carry the claim. For
#: layering that produced a permanent violation on the most natural thing a user
#: can model (a decision linking the issue that motivated it); for cycles it
#: turned a mutually-referencing pair into a permanent warning, 127 of them on
#: this store. A warning that fires on correct usage teaches people to ignore
#: the whole of `docs check`, which is where the duplicate-id detection lives.
#: Findings that mean the corpus is *broken* — a document is unreachable, or an
#: edge resolves to nothing. These are what a merge gate must stop.
ERROR_KINDS: frozenset[str] = frozenset({"duplicate-id", "dangling", "malformed"})

#: Everything else (`orphan`, `cycle`, `layering`, `stale`, `unknown-type`,
#: `unknown-status`, `unknown-tag`, `tag-key-format`, `unmatched-code`,
#: `missing-required`)
#: describes shape or classification, not
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
#:
#: `missing-required` is a warning on the same argument, sharpened: the schema
#: change that creates it arrives *from the package*, so a corpus that passed
#: yesterday can fail today with no commit to point at. An error there would
#: red-build every repo on the release that added the field, which is precisely
#: the failure the two rules above were written to avoid.
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
        code_matches: Mapping[str, bool] | None = None,
    ) -> list[CheckIssue]:
        """Run every Tier 1 check over the indexed corpus.

        ``known_tags`` is the tag registry; ``None`` skips the tag check, the
        same permissive-when-absent convention the relation-kind registry uses.
        ``code_matches`` says which ``code`` globs still name something on disk
        and is ``None`` when there is no repository to ask — a global store
        would otherwise report every pattern in it as missing.
        """
        issues: list[CheckIssue] = []
        issues.extend(self._find_unknown_type(documents))
        issues.extend(self._find_unknown_status(documents))
        issues.extend(self._find_missing_required(documents))
        if known_tags is not None:
            issues.extend(self._find_unknown_tag(documents, known_tags))
            issues.extend(self._find_tag_key_format(known_tags))
        issues.extend(self._find_dangling(documents, relations))
        issues.extend(self._find_cycles(relations))
        issues.extend(self._find_orphans(documents, relations))
        issues.extend(self._find_layering_violations(documents, relations))
        if today is not None:
            issues.extend(self._find_stale(documents, today))
        if code_matches is not None:
            issues.extend(self._find_unmatched_code(documents, code_matches))
        return issues

    def _find_unmatched_code(
        self, documents: list[Document], code_matches: Mapping[str, bool]
    ) -> list[CheckIssue]:
        """Flag ``code`` globs that no longer name anything in the repository.

        The Tier 1 half of the code linkage: the write path deliberately accepts
        a pattern that matches nothing, because a decision is often written
        before the code it decides — so the question "does it match *now*" has
        to be asked later, by the command that reports shape and age, and as a
        warning. It is not damage: the document is intact, the graph resolves,
        and the honest reading is "the code moved, or was never written, and
        somebody should look".

        Nothing repairs it either, which is why it stays out of ``check --fix``:
        only a human knows whether the glob is stale or the document is.

        ``code_matches`` is the resolved answer per pattern, computed against
        the working tree by the caller — the domain stays pure and testable
        without a repository. A pattern *absent* from the map is unresolved
        rather than missing, and is not reported: the same rule ``similarity``
        follows on the read paths, where absent means "not scored" and never
        "scored zero". A finding invented for a question nobody answered is the
        failure mode this whole check has to avoid.
        """
        issues: list[CheckIssue] = []
        for doc in documents:
            if doc.archived:
                continue
            missing = [pattern for pattern in doc.code if not code_matches.get(pattern, True)]
            if not missing:
                continue
            joined = ", ".join(repr(pattern) for pattern in missing)
            issues.append(
                CheckIssue(
                    kind="unmatched-code",
                    message=(
                        f"{doc.id!r} governs {joined}, which matches nothing in the "
                        f"repository; update the pattern with `docir update {doc.id} "
                        f"--set-code ...` or re-verify the document"
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

    def _find_tag_key_format(self, known_tags: frozenset[str]) -> list[CheckIssue]:
        """Flag registered keys the vocabulary grammar does not allow.

        A finding about the *registry*, not about any document, so ``doc_ids``
        is empty — the offending key is named in the message instead.

        A warning, and it has to stay one. `tag add` rejects a bad key now, so
        the only way to hold one is to predate the rule, and an existing corpus
        must not start failing a `--strict` build for something its author
        could not have avoided. Nothing repairs it either: the fix is a rename,
        and only a human knows whether `Auth` meant `auth` or `authn`.
        """
        offenders = sorted(key for key in known_tags if not is_valid_tag_key(key))
        return [
            CheckIssue(
                kind="tag-key-format",
                message=(
                    f"registered tag {key!r} is not {TAG_KEY_RULE}; "
                    f"rename it with `docir tag rename {key} <new-key>` "
                    "(`--merge` if the target already exists)"
                ),
                doc_ids=(),
            )
            for key in offenders
        ]

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
            # Only a kind with a *direction* can form a loop worth reporting. A
            # symmetric kind says the same thing both ways, so a pair of
            # documents that reference each other is modelled correctly rather
            # than cyclically; the schema decides which is which
            # (`RelationKindSchema.symmetric`).
            #
            # A *self*-edge is the exception and is reported whatever its kind:
            # symmetry is what makes a mutual pair legitimate, and it is exactly
            # what makes "A relates to A" empty. The write path rejects one, so
            # this is the only thing that sees a self-edge a merge or a
            # hand-edit put on disk (issue-2ebfc018f29a).
            if rel.source == rel.target or not self._schema.is_symmetric_relation(rel.kind):
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
            if not self._schema.is_dependency_relation(rel.kind):
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
