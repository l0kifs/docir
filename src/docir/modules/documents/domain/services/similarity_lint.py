"""Tier 2 advisory checks — heuristic, opt-in, never CI-blocking.

Run only when a human chooses to (``docir lint --deep``). Reuses the same
fastembed vectors already computed for ``docir context`` to flag content
similarity (DRY at the idea level), plus a simple document-size heuristic for
scope creep (an SRP smell). Everything here is a suggestion, never an error.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.schema import Schema
from docir.modules.documents.domain.services.chunking import split_body
from docir.platform.embedding.vector import Embedding


@dataclass(frozen=True, slots=True)
class LintFinding:
    """One advisory finding with a severity-free descriptive message."""

    kind: str
    message: str
    doc_ids: tuple[str, ...]


class SimilarityLinter:
    """Computes Tier 2 advisory findings from embeddings and document size."""

    def __init__(self, similarity_threshold: float = 0.9, size_threshold_chars: int = 8000) -> None:
        self._similarity_threshold = similarity_threshold
        self._size_threshold = size_threshold_chars

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

    def _threshold_for(self, doc_type: str, schema: Schema | None) -> int:
        """The body-size threshold for a type; ``0`` disables the check for it."""
        if schema is None or doc_type not in schema.types:
            return self._size_threshold
        configured = schema.types[doc_type].max_body_chars
        return self._size_threshold if configured is None else configured
