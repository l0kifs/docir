"""Tier 2 advisory checks — heuristic, opt-in, never CI-blocking.

Run only when a human chooses to (``docs lint --deep``). Reuses the same
fastembed vectors already computed for ``docs context`` to flag content
similarity (DRY at the idea level), plus a simple document-size heuristic for
scope creep (an SRP smell). Everything here is a suggestion, never an error.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from docir.modules.documents.domain.entities.document import Document
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
        (GAP-055).

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

    def find_scope_creep(self, documents: list[Document]) -> list[LintFinding]:
        """Flag documents whose body is large enough to smell like scope creep."""
        findings: list[LintFinding] = []
        for doc in documents:
            if len(doc.body) > self._size_threshold:
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
