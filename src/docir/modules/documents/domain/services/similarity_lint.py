"""Tier 2 advisory checks — heuristic, opt-in, never CI-blocking.

Run only when a human chooses to (``docir lint --deep``). Reuses the same
fastembed vectors already computed for ``docir context`` to flag content
similarity (DRY at the idea level), plus a simple document-size heuristic for
scope creep (an SRP smell). Everything here is a suggestion, never an error.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.schema import Schema
from docir.modules.documents.domain.services.chunking import split_body
from docir.modules.documents.domain.services.expressions import compile_expression
from docir.modules.documents.domain.services.markdown_headings import scan_headings
from docir.platform.embedding.vector import Embedding
from docir.platform.errors import ValidationError

#: A quoted phrase long enough, and capitalised enough, to be a section name.
#: Both quote styles, because prose in this corpus uses each.
_QUOTED = re.compile(r'["“]([A-Z][^"”\n]{5,60})["”]')

#: How far before a quoted heading a document id may sit and still count as
#: qualifying it. One clause — `` `adr-0001`, "Context" `` — not a paragraph.
_QUALIFY_WINDOW = 40


@dataclass(frozen=True, slots=True)
class LintFinding:
    """One advisory finding with a severity-free descriptive message."""

    kind: str
    message: str
    doc_ids: tuple[str, ...]


#: An explicit `--expr` argument in prose. Deliberately narrow: see
#: :meth:`SimilarityLinter.find_broken_expressions` for what a wider net caught.
_EXPR_ARG_RE = re.compile(r'--expr\s+"([^"]+)"')


class SimilarityLinter:
    """Computes Tier 2 advisory findings from embeddings and document size."""

    def __init__(self, similarity_threshold: float = 0.9, size_threshold_chars: int = 8000) -> None:
        self._similarity_threshold = similarity_threshold
        self._size_threshold = size_threshold_chars

    def find_unresolved_mentions(self, unresolved: Sequence[tuple[str, str]]) -> list[LintFinding]:
        """Report ids named in prose that no document carries.

        Tier 2, and it can never be promoted. Measured on this project's own
        corpus: all 47 were documentation *examples* — `adr-0007`,
        `adr-3f9a2b1c7d4e` and the rest, sitting in the architecture documents
        that explain what an id looks like. A Tier 1 warning would fire 47 times
        on a healthy corpus, every one a false positive, loudest on the
        documents doing their job (adr-e86c5040d626).

        Ignoring ids inside code spans does not rescue it, and was measured too:
        20 of the 47 sit outside code anyway, while 56 *resolved* mentions live
        only inside code spans — so the filter would keep most of the noise and
        delete 12% of the working graph.

        What is left is a genuine but low-yield question — "is this a typo?" —
        which is exactly what Tier 2 is: opt-in, advisory, never an exit code.
        One finding per document rather than per id, because the answer a reader
        wants is "which of my documents cite something missing", and a document
        explaining the id format would otherwise produce five identical lines.
        """
        by_source: dict[str, list[str]] = {}
        for source, target in unresolved:
            by_source.setdefault(source, []).append(target)
        return [
            LintFinding(
                kind="unresolved-mention",
                message=(
                    f"{source!r} names {', '.join(repr(t) for t in sorted(set(targets)))}, "
                    f"which no document carries — a typo, a deleted document, or an "
                    f"example id written on purpose"
                ),
                doc_ids=(source,),
            )
            for source, targets in sorted(by_source.items())
        ]

    def find_duplicates(
        self,
        vectors: list[tuple[str, Embedding]],
        linked_pairs: Collection[frozenset[str]] = (),
    ) -> list[LintFinding]:
        """Flag document pairs whose vectors exceed the similarity threshold.

        A pair joined by a relation is skipped. "These two are similar" is
        answered by the edge already in the file — the author has modelled the
        connection, which is what typed edges are *for* — so reporting it leaves
        the reader nothing to do but delete a document or unlink a correct
        relation. Measured against docir's own corpus, every one of the 14
        duplicate findings was such a pair: a `Q-0NN` question and the `GAP-0NN`
        it came from, linked precisely to say they are about the same thing
        (issue-08437ba704ff).

        The case worth keeping is the unlinked one — two documents nobody has
        noticed are about the same thing — which is the copy-paste this check
        exists to catch. Direction does not matter, so pairs are compared as
        unordered sets.

        ``linked_pairs`` defaults to empty rather than being required: this is a
        pure domain service, and a caller that has no relation graph to offer
        should get the unfiltered answer rather than a signature it cannot
        satisfy.
        """
        linked = set(linked_pairs)
        findings: list[LintFinding] = []
        for i in range(len(vectors)):
            id_a, vec_a = vectors[i]
            for j in range(i + 1, len(vectors)):
                id_b, vec_b = vectors[j]
                if frozenset((id_a, id_b)) in linked:
                    continue
                similarity = vec_a.cosine_similarity(vec_b)
                if similarity >= self._similarity_threshold:
                    findings.append(
                        LintFinding(
                            kind="duplicate",
                            message=(
                                f"{id_a!r} and {id_b!r} are highly similar "
                                f"(cosine {similarity:.2f}) — possible DRY "
                                f"violation"
                            ),
                            doc_ids=(id_a, id_b),
                        )
                    )
        return findings

    def find_scope_creep(
        self, documents: list[Document], schema: Schema | None = None
    ) -> list[LintFinding]:
        """Flag documents whose body is large enough to smell like scope creep.

        The threshold is per type. One constant for every type made a glossary,
        a rule register and a probe log permanently "too long" — and a register
        split in half is two half-registers, so the advice could not be taken
        (issue-5d6a5e854d11). A type may set ``max_body_chars`` in the schema, with ``0``
        meaning never; absent, it inherits this linter's default.

        ``schema`` is optional for the same reason ``linked_pairs`` is: a caller
        with no schema to offer gets the flat default rather than a signature it
        cannot satisfy.
        """
        findings: list[LintFinding] = []
        for doc in documents:
            threshold = self._threshold_for(doc.type, schema)
            if threshold and len(doc.body) > threshold:
                findings.append(
                    LintFinding(
                        kind="scope-creep",
                        message=(
                            f"{doc.id!r} body is {len(doc.body)} chars — consider splitting (SRP)"
                        ),
                        doc_ids=(doc.id,),
                    )
                )
        return findings

    def find_oversized_sections(self, documents: list[Document]) -> list[LintFinding]:
        """Flag sections the chunker has to split, and so cannot fully address.

        Not a taste threshold: the check *runs the splitter* and reports what it
        actually produced. A section over :data:`MAX_CHUNK_CHARS` is cut into
        pieces, and only the first keeps the heading — so the rest is text that
        `context` can retrieve but `matched_section` can never name and
        ``get --section`` will not return on its own. The number behind it is
        derived from the measured model window (adr-927aa43d9635), which is why
        this check has no threshold of its own to tune.

        Tier 2 on purpose, and it stays there. A long section is a *smell*: a
        reference table split in half is two half-tables, and the fix for one of
        those is to leave it alone — the same argument ``max_body_chars`` exists
        for (issue-5d6a5e854d11). It reports the shape and lets a human decide.
        """
        findings: list[LintFinding] = []
        for doc in documents:
            heading, orphaned = "", 0
            counts: list[tuple[str, int]] = []
            for chunk in split_body(doc.body):
                if chunk.heading:
                    if orphaned:
                        counts.append((heading, orphaned))
                    heading, orphaned = chunk.heading, 0
                elif heading:
                    orphaned += 1
            if orphaned:
                counts.append((heading, orphaned))
            findings += [
                LintFinding(
                    kind="oversized-section",
                    message=(
                        f"{doc.id!r} section {name!r} is split into {pieces + 1} chunks — "
                        f"{pieces} of them nothing can address by heading"
                    ),
                    doc_ids=(doc.id,),
                )
                for name, pieces in counts
            ]
        return findings

    def find_broken_expressions(self, documents: list[Document]) -> list[LintFinding]:
        """Flag a documented ``--expr`` argument that would not run.

        Every other invocation docir documents is checked for *shape* — the
        command exists, the flag exists. `--expr` is the one flag whose argument
        is a language, and a wrong expression looks exactly like a right one
        until somebody runs it. Two failures are silent rather than loud: a bare
        `null` is an identifier and not a literal, so `owner == null` compares a
        key nothing carries against itself and returns the answer the author
        wanted for the wrong reason; and a name the projection lacks evaluates
        to null, so a typo matches nothing and reads as a clean corpus.

        Scoped to an explicit --expr followed by a quoted argument, not to anything
        expression-shaped. Sweeping backticked spans over this project's own
        corpus found 18 candidates and 13 apparent failures, of which one was
        real — the rest were quoted assertions, error messages and prose
        comparisons like ``old == new``. Text does not distinguish an expression
        from a sentence about one; an invocation does.

        A shell example escapes its backticks, because a backtick inside double
        quotes is command substitution — so the argument is unescaped before it
        is compiled, or correct documentation would fail.

        Tier 2 and staying there: a document may quote a deliberately wrong
        expression to explain why it is wrong.
        """
        findings: list[LintFinding] = []
        for doc in documents:
            for raw in _EXPR_ARG_RE.findall(doc.body):
                expression = raw.replace("\\`", "`")
                try:
                    compile_expression(expression)
                except ValidationError as exc:
                    findings.append(
                        LintFinding(
                            kind="broken-expression",
                            message=(
                                f"{doc.id!r} documents --expr {expression!r}, which will not "
                                f"run: {exc}"
                            ),
                            doc_ids=(doc.id,),
                        )
                    )
        return findings

    def find_ambiguous_headings(self, documents: list[Document]) -> list[LintFinding]:
        """Flag a heading used twice in one document, which ``--section`` cannot split.

        Section reads resolve to the *first* match, so the later one is reachable
        only by fetching the whole body — the cost the flag exists to remove. It
        stays advisory because first-match is the right resolution rule: the
        defect is that the condition is silent, not that the behaviour is wrong,
        and a corpus can acquire one through a permitted hand-edit at any time
        (issue-71555a89a73d).
        """
        findings: list[LintFinding] = []
        for doc in documents:
            counts = Counter(h.text for h in scan_headings(doc.body) if h.level >= 2)
            findings += [
                LintFinding(
                    kind="ambiguous-heading",
                    message=(
                        f"{doc.id!r} uses the heading {name!r} {n} times — a section read "
                        f"resolves to the first, so the rest are unreachable by name"
                    ),
                    doc_ids=(doc.id,),
                )
                for name, n in counts.items()
                if n > 1
            ]
        return findings

    def find_unqualified_section_refs(self, documents: list[Document]) -> list[LintFinding]:
        """Flag prose naming a section that lives in a *different* document.

        The failure mode a split leaves behind: text saying `see "Archiving vs.
        deletion" below` keeps reading as though the section were local long
        after it moved to a sibling, and no existing check looks at prose.

        Deliberately narrow, because the input is a regex over quoted phrases. A
        finding needs all three: the phrase is not a heading *here*, it is a
        heading *somewhere*, and the owning document's id is not already beside
        it. A reference that names its document is what the fix looks like, so
        recognising it is what keeps the check quiet once acted on.

        **Only headings unique to one document count.** Dropping that, the first
        run reported two findings and both were wrong: `Resolution` is a heading
        in dozens of issues, so quoting the word at all was enough to trip it,
        and where several documents share a name the "it lives in X" clause
        picked one arbitrarily and named the wrong document. A check that cannot
        say *which* document is not entitled to the sentence.
        """
        seen_in: dict[str, set[str]] = {}
        for doc in documents:
            for heading in scan_headings(doc.body):
                seen_in.setdefault(heading.text, set()).add(doc.id)
        owners = {name: next(iter(docs)) for name, docs in seen_in.items() if len(docs) == 1}

        findings: list[LintFinding] = []
        for doc in documents:
            local = {h.text for h in scan_headings(doc.body)}
            seen: set[str] = set()
            for match in _QUOTED.finditer(doc.body):
                name = match.group(1)
                owner = owners.get(name)
                if owner is None or owner == doc.id or name in local or name in seen:
                    continue
                if owner in doc.body[max(0, match.start() - _QUALIFY_WINDOW) : match.start()]:
                    continue
                seen.add(name)
                findings.append(
                    LintFinding(
                        kind="unqualified-section-ref",
                        message=(
                            f"{doc.id!r} names the section {name!r} without saying where it "
                            f"is — it lives in {owner!r}"
                        ),
                        doc_ids=(doc.id, owner),
                    )
                )
        return findings

    def _threshold_for(self, doc_type: str, schema: Schema | None) -> int:
        """The body-size threshold for a type; ``0`` disables the check for it."""
        if schema is None or doc_type not in schema.types:
            return self._size_threshold
        configured = schema.types[doc_type].max_body_chars
        return self._size_threshold if configured is None else configured
