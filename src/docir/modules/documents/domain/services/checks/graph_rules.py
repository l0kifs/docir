"""The findings that read the **authored** relation graph.

Seven rules over ``related:`` and the prose links beside it. None of them reads
the derived mention graph: ``orphan`` was the one that did, and prose that names
an orphan is usually the triage of it.
"""

from __future__ import annotations

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.entities.relation import Relation
from docir.modules.documents.domain.schema import Schema
from docir.modules.documents.domain.services.checks.findings import CheckIssue
from docir.modules.documents.domain.services.expressions import (
    EdgeView,
    compile_expression,
    matches,
    project,
)
from docir.platform.naming.links import (
    LinkIndex,
    LinkResolution,
    LinkTarget,
    scan_wikilinks,
)

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


class GraphShapeChecks:
    """Cycles, orphans, layering, dead edges and custom store rules."""

    def __init__(self, schema: Schema) -> None:
        self._schema = schema

    def run(self, documents: list[Document], relations: list[Relation]) -> list[CheckIssue]:
        """Every graph-shape finding, in the order ``check`` reports them."""
        issues: list[CheckIssue] = []
        issues.extend(self._find_dangling(documents, relations))
        issues.extend(self._find_unresolved_links(documents))
        issues.extend(self._find_cycles(relations))
        issues.extend(self._find_orphans(documents, relations))
        issues.extend(self._find_layering_violations(documents, relations))
        issues.extend(self._find_unblocked(documents, relations))
        issues.extend(self._find_store_checks(documents, relations))
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

    def _find_unresolved_links(self, documents: list[Document]) -> list[CheckIssue]:
        """Flag ``[[...]]`` prose links whose target is no document.

        The same defect as ``dangling`` in the other syntax, and a *warning*
        rather than an error for a reason: a `related:` edge is a declared,
        typed claim the write path validated, so one that resolves to nothing
        means the corpus was damaged after the fact. A prose link is
        navigational — it carries no kind, gates no merge and feeds no graph —
        so a broken one costs a reader a click, not a wrong decision.

        **Why this is Tier 1 when `unresolved-mention` is not.** They look like
        the same check and are not. An id *named* in a sentence is a citation:
        writing `adr-0007` while explaining the id format is correct usage, and
        measured on this corpus all 47 unresolved mentions were exactly that, so
        the warning would fire only on documents doing their job
        (adr-e86c5040d626). `[[...]]` is not a citation. It is link syntax and
        has no second reading — whoever typed the brackets meant to point at a
        document, so one that points at nothing is a defect by construction. The
        one false positive available, a body demonstrating the syntax, is
        already excluded because :func:`scan_wikilinks` skips code, and that
        filter costs nothing here where it would have cost the mention graph
        12% of its edges.

        Resolution reads **every** document, archived and inactive included: a
        link to a resolved issue or a superseded decision works, and following
        one is the point of publishing the graph. Only the *sources* are
        filtered — an archived document's broken links are nobody's queue.

        Nothing repairs it, which keeps it out of ``check --fix``: a target that
        resolves to nothing needs somebody to say which document was meant, and
        a repair has nothing to read *with*. The near-miss the finding was built
        from is a slug guessed one word short of the title, which no rule can
        distinguish from a link to a document not written yet.
        """
        index = LinkIndex(
            LinkTarget(doc_id=doc.id, title=doc.title, stem=_stem(doc.path)) for doc in documents
        )
        issues: list[CheckIssue] = []
        for doc in documents:
            if doc.archived:
                continue
            seen: set[str] = set()
            for link in scan_wikilinks(doc.body):
                resolution = index.resolve(link.target)
                if resolution.doc_id is not None or link.target in seen:
                    continue
                seen.add(link.target)
                issues.append(
                    CheckIssue(
                        kind="unresolved-link",
                        message=_unresolved_link_message(doc.id, link.target, resolution),
                        doc_ids=(doc.id,),
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


def _stem(path: str | None) -> str:
    """The filename stem of a stored document, or ``""`` before it has one."""
    if not path:
        return ""
    return path.replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".md")


def _unresolved_link_message(doc_id: str, target: str, resolution: LinkResolution) -> str:
    """What to tell whoever has to fix the link.

    An ambiguous target and a missing one are different problems with different
    repairs — disambiguate, or find the document — so they do not share a
    sentence. Both name the command that produces the right target, because the
    failure this check exists for is somebody typing a slug from memory.
    """
    if resolution.is_ambiguous:
        joined = ", ".join(repr(candidate) for candidate in resolution.candidates)
        return (
            f"{doc_id!r} links to [[{target}]], which names {len(resolution.candidates)} "
            f"documents ({joined}) — link the id instead"
        )
    return (
        f"{doc_id!r} links to [[{target}]], which names no document — "
        f"find it with `docir search {target.replace('-', ' ')!r}` and link its id"
    )
