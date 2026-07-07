"""Tier 2 advisory checks — heuristic, opt-in, never CI-blocking.

Run only when a human chooses to (``docs lint --deep``). Reuses the same
fastembed vectors already computed for ``docs context`` to flag content
similarity (DRY at the idea level), plus a simple document-size heuristic for
scope creep (an SRP smell). Everything here is a suggestion, never an error.
"""

from __future__ import annotations

from dataclasses import dataclass

from docir.domain.entities.document import Document
from docir.domain.value_objects.embedding import Embedding


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

    def find_duplicates(self, vectors: list[tuple[str, Embedding]]) -> list[LintFinding]:
        """Flag document pairs whose vectors exceed the similarity threshold."""
        findings: list[LintFinding] = []
        for i in range(len(vectors)):
            id_a, vec_a = vectors[i]
            for j in range(i + 1, len(vectors)):
                id_b, vec_b = vectors[j]
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
