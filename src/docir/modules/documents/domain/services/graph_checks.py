"""Tier 1 structural checks — graph-level warnings, never write-blocking.

Run on demand (``docir check``) or in CI, these surface graph-shape problems as
warnings rather than failing an agent mid-task:

* cycles in the relation graph,
* orphan documents (no incoming or outgoing relations),
* layering violations — a higher-level type *depending on* a lower-level one,
* unblocked documents — every dependency they declared is now closed,
* stale documents — past their type's review cadence (when a date is supplied).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.entities.relation import Relation
from docir.modules.documents.domain.schema import Schema
from docir.modules.documents.domain.services.expressions import (
    EdgeView,
    compile_expression,
    matches,
    project,
)
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
#: the whole of `docir check`, which is where the duplicate-id detection lives.
#: Findings that mean the corpus is *broken* — a document is unreachable, or an
#: edge resolves to nothing. These are what a merge gate must stop.
#:
#: `empty-index` is the one that does not describe damage to the corpus, and it
#: earns the severity by a different argument: it means `check` *could not look*.
#: The graph half reads the index, so with none built every structural finding is
#: silent and `--strict` exits 0 — a merge gate that passes because it read
#: nothing, which is strictly worse than no gate (issue-87410666c867). The
#: warnings this file argues against promoting all red-build a *correct* setup;
#: this one red-builds a setup that was never checking anything, and names the
#: single command that fixes it.
ERROR_KINDS: frozenset[str] = frozenset({"duplicate-id", "dangling", "malformed", "empty-index"})

#: Every finding kind docir defines. A store's own check may not take one of
#: these names: a check called `dangling` would make `--strict`'s behaviour
#: depend on whose schema is loaded, and a store's rule must never be able to
#: change what a docir finding means. The loader refuses the collision.
RESERVED_FINDING_KINDS: frozenset[str] = frozenset(
    {
        "duplicate-id",
        "dangling",
        "malformed",
        "orphan",
        "cycle",
        "layering",
        "stale",
        "unblocked",
        "unmatched-code",
        "code-changed",
        "tag-key-format",
        "unknown-type",
        "unknown-status",
        "unknown-tag",
        "unknown-relation-kind",
        "missing-required",
        "schema-drift",
        "stale-index-build",
        "empty-index",
    }
)

#: Everything else (`orphan`, `cycle`, `layering`, `stale`, `unknown-type`,
#: `unknown-status`, `unknown-tag`, `tag-key-format`, `unmatched-code`,
#: `code-changed`, `missing-required`, `unknown-relation-kind`, `schema-drift`,
#: `stale-index-build`, `unblocked`)
#: describes shape or classification, not
#: damage. `orphan` in particular fires for any document with no relations — the
#: default state of a new one — so treating these as build failures made the gate
#: unusable on a healthy corpus.
#:
#: `unknown-relation-kind` joins them on the same grounds and one more: the edge
#: keeps working. `Schema.relation_kind` falls back to the core properties, so a
#: kind the registry has stopped listing is still cycle-checked and still read as
#: a dependency — the corpus is intact and only the registry has fallen behind it.
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
            issues.extend(self._find_unknown_tag(documents, known_tags))
            issues.extend(self._find_tag_key_format(known_tags))
        issues.extend(self._find_dangling(documents, relations))
        issues.extend(self._find_cycles(relations))
        issues.extend(self._find_orphans(documents, relations))
        issues.extend(self._find_layering_violations(documents, relations))
        issues.extend(self._find_unblocked(documents, relations))
        issues.extend(self._find_store_checks(documents, relations))
        if today is not None:
            issues.extend(self._find_stale(documents, today))
        if code_matches is not None:
            issues.extend(self._find_unmatched_code(documents, code_matches))
        if code_digests is not None:
            issues.extend(self._find_changed_code(documents, code_digests))
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
        issues: list[CheckIssue] = []
        issues.extend(self._find_unknown_type(documents))
        issues.extend(self._find_unknown_status(documents))
        issues.extend(self._find_missing_required(documents))
        issues.extend(self._find_unknown_relation_kind(relations))
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
        the fix is a decision — repoint the pattern, or rewrite the document the
        moved code has outdated — and a repair has nothing to read *with*.
        Whoever drives the CLI makes that call, which is why the finding names
        the pattern rather than just the document.

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

    def _find_changed_code(
        self, documents: list[Document], code_digests: Mapping[str, str]
    ) -> list[CheckIssue]:
        """Flag documents whose governed code has moved since they were verified.

        The evidence half of staleness. ``stale`` measures a calendar — a review
        cadence elapsed — and so fires on documents nothing has happened to
        while staying silent on the one that was rewritten underneath yesterday.
        This asks the other question, and it is the sharper one: the code this
        document describes is not the code somebody read.

        A warning, and it must stay one. It fires from a *comparison against the
        working tree*, so a branch that legitimately edits the code before
        updating the docs — the ordinary shape of a change — would fail its own
        CI, which is how a gate teaches people to stop reading `docir check`.

        Clearing it is a **judgement, not a rewrite**: somebody has to read the
        document against the code as it now stands and decide it is still true.
        That is why `check --fix` cannot touch it — a repair has nothing to read
        *with* — and it is the whole of the rule. Not "a human did it": docir's
        writer is an agent by design (thesis 2), so a signal only a human could
        emit is a signal nothing would ever emit. What the rule excludes is the
        writer that clears the finding *inside the task that moved the code*,
        certifying its own change; that degrades `verified` from "somebody read
        this" to "CI is green", which is the laundering adr-bd7c4f3c5764 guards
        against, arriving by a different door.

        Three absences are all read as *unknown*, never as unchanged. A pattern
        missing from ``code_digests`` did not resolve (it matches nothing — the
        `unmatched-code` finding covers that, and reporting both would name one
        problem twice). A pattern with no recorded digest was never verified.
        And a document with no digests at all has never been verified with a
        matcher present.
        """
        issues: list[CheckIssue] = []
        for doc in documents:
            if doc.archived or not doc.verified_code:
                continue
            moved = [
                pattern
                for pattern in doc.code
                if (current := code_digests.get(pattern)) is not None
                and (recorded := doc.verified_code.get(pattern)) is not None
                and current != recorded
            ]
            if not moved:
                continue
            joined = ", ".join(repr(pattern) for pattern in moved)
            verified_on = "" if doc.verified is None else f" on {doc.verified.isoformat()}"
            issues.append(
                CheckIssue(
                    kind="code-changed",
                    message=(
                        f"{doc.id!r} governs {joined}, which changed since it was "
                        f"verified{verified_on}; re-read it and run `docir update "
                        f"{doc.id} --verified`"
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
        and deciding whether `Auth` meant `auth` or `authn` is a reading of the
        corpus, not a transformation of it.
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

        Staleness is honest re-verification, not a heuristic: a type opts
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
        """Flag documents no **authored** edge connects, in either direction.

        Prose does not count, and that is the correction issue-77a09761e1d4
        made. This check read the derived mention graph too, so an id named in
        any body cleared it — and the body most likely to name a queue of orphan
        ids is the triage that diagnoses them. Writing down "these four still
        need wiring" therefore emptied the queue that tracked those four, which
        makes the finding measure where somebody happened to type an id rather
        than whether the document is connected. A judgement about a queue must
        not empty it.

        The false positive that put mentions here in the first place — a warning
        on a document its author linked in a sentence — is real, and is now
        answered by :attr:`Document.isolated` instead: a reviewed exemption
        somebody wrote on purpose, rather than a side effect of prose. The
        alternative, a mention clearing the finding, cannot tell the two apart,
        because "this id is fine unlinked" and "this id is still unwired" are
        written in exactly the same characters.

        Being cited still counts as much as citing — the check reads both
        directions of ``related:``, as it always has.
        """
        connected: set[str] = set()
        for rel in relations:
            connected.add(rel.source)
            connected.add(rel.target)
        issues: list[CheckIssue] = []
        for doc in documents:
            # An exempt document is not reported and not counted: `isolated` is
            # the recorded answer to this finding, so re-asking is the noise it
            # was written to remove.
            if doc.archived or doc.isolated:
                continue
            if doc.id not in connected:
                issues.append(
                    CheckIssue(
                        kind="orphan",
                        message=(
                            f"orphan document {doc.id!r} has no relations — link it with "
                            f"`docir update {doc.id} --set-related <id>:<kind>`, or record why "
                            f"it stands alone with `--set-isolated '<reason>'`"
                        ),
                        doc_ids=(doc.id,),
                    )
                )
        return issues

    def _find_store_checks(
        self, documents: list[Document], relations: list[Relation]
    ) -> list[CheckIssue]:
        """Evaluate the rules the *store* declared in its own schema.

        docir ships none of these. The grammar is docir's and every rule written
        in it is the store's, which is the line adr-b2cfed9d5888 drew: docir
        refused to have opinions about your architecture, not to let you state
        yours. A shipped default expression here would cross back.

        Always a **warning**, whatever the rule says. `ERROR_KINDS` means "the
        corpus is broken" in docir's terms and gates a merge; a store that wants
        its own rules fatal has `--strict-all`, which already means exactly
        that. Letting a declared check into the error set would make `--strict`
        mean something different in every repository.

        Each document is projected the same way `query --expr` projects it — one
        shape for both, because a rule is written by trying it as a query first
        and would otherwise mean something subtly different once declared.
        """
        if not self._schema.checks:
            return []
        by_id = {doc.id: doc for doc in documents}
        outgoing: dict[str, list[EdgeView]] = {}
        incoming: dict[str, list[EdgeView]] = {}
        for rel in relations:
            target = by_id.get(rel.target)
            source = by_id.get(rel.source)
            outgoing.setdefault(rel.source, []).append(
                {
                    "to": rel.target,
                    "kind": rel.kind,
                    "type": target.type if target else None,
                    "status": target.status if target else None,
                }
            )
            incoming.setdefault(rel.target, []).append(
                {
                    "to": rel.source,
                    "kind": rel.kind,
                    "type": source.type if source else None,
                    "status": source.status if source else None,
                }
            )

        issues: list[CheckIssue] = []
        for check in self._schema.checks:
            compiled = compile_expression(check.expression)
            for document in documents:
                projection = project(
                    document,
                    stale=False,
                    outgoing=outgoing.get(document.id, []),
                    incoming=incoming.get(document.id, []),
                )
                if matches(compiled, projection):
                    issues.append(
                        CheckIssue(
                            kind=check.name,
                            message=f"{document.id!r}: {check.message}",
                            doc_ids=(document.id,),
                        )
                    )
        return issues

    def _find_unblocked(
        self, documents: list[Document], relations: list[Relation]
    ) -> list[CheckIssue]:
        """Live documents whose every declared dependency has since closed.

        The one finding here that reports *good* news, and it exists because
        nothing else does. A ``depends_on`` edge is a claim that this work waits
        on that work, and until now only ``context`` expansion ever read it —
        and only if a caller happened to query nearby. So a blocker could clear
        and the thing it blocked would sit there, with the graph holding the
        answer and no reader asking (issue-fd086c0c6ab0 waited on a resolved
        issue for two commits before anyone noticed).

        "Closed" is the type's own ``inactive_statuses``, or archived — the same
        definition the read paths use to hide a document, so a corpus cannot
        disagree with itself about what done means. A document with **no**
        dependencies is not unblocked, it is unconstrained, and reporting it
        would fire on most of the corpus.

        Which kinds count is schema data rather than a name — but the property
        is ``blocking``, not ``dependency``. Reading ``dependency`` here was the
        first version and it was wrong: that property is *structural*, about
        where two types sit relative to each other, and this question is
        *temporal*. ``refines`` is a dependency and not a blocker, so a decision
        refining a **superseded** one was announced as ready to start — a
        problem reported as good news (adr-716c2eeb4e51).

        A warning, never an error — nothing is broken, this is a scheduling
        fact, and like ``stale`` it is cleared by doing something real rather
        than by a flag: start the work, or drop an edge no longer true.
        """
        inactive = self._schema.inactive_statuses()
        by_id = {doc.id: doc for doc in documents}

        def closed(doc_id: str) -> bool:
            target = by_id.get(doc_id)
            # A target nothing carries is `dangling`, reported there. Treating
            # it as closed would turn a broken edge into a green light.
            return target is not None and (target.archived or target.status in inactive)

        blockers: dict[str, list[str]] = {}
        for rel in relations:
            # Every dependency edge, including one whose target is missing.
            # Filtering those out here looked defensive and was the opposite: a
            # document depending on one resolved issue and one *dangling* edge
            # would have arrived with a single satisfied blocker and been
            # announced as ready to start.
            if self._schema.is_blocking_relation(rel.kind):
                blockers.setdefault(rel.source, []).append(rel.target)

        issues: list[CheckIssue] = []
        for source, targets in sorted(blockers.items()):
            document = by_id.get(source)
            if document is None or document.archived or document.status in inactive:
                continue
            if not all(closed(target) for target in targets):
                continue
            listed = ", ".join(repr(target) for target in sorted(set(targets)))
            issues.append(
                CheckIssue(
                    kind="unblocked",
                    message=(
                        f"{source!r} is ready to start: everything it depends on "
                        f"has closed ({listed})"
                    ),
                    doc_ids=(source, *sorted(set(targets))),
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
