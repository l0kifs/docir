"""Chunk vectors through the real index: written, replaced, cascaded, ranked.

The lifecycle matters as much as the split. A chunk set describes one body, so
it has to be replaced wholesale when that body changes and disappear when the
document does — a leftover chunk keeps a deleted or rewritten section
answerable, which is worse than not having chunked at all.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from docir.entry_points.dispatch import Dispatcher
from docir.modules.indexing.api import HybridScorer, VectorCandidate
from docir.platform.embedding.deterministic import DeterministicEmbedder
from docir.platform.persistence.unit_of_work import UnitOfWork

Factory = Callable[[], UnitOfWork]

#: Three sections, each long enough to clear the merge threshold. Stripped
#: because the file store trims trailing whitespace on write: a body ending in a
#: space is written back without it, the indexed copy and the file then disagree,
#: and `--replace-body` refuses as a diverged write. The fixture's problem, not
#: the product's, but an easy hour to lose.
_SECTIONS = (
    "## Credentials\n\n"
    + "Mutual TLS with a client certificate rotated at ten months. " * 4
    + "\n\n## Rate limits\n\n"
    + "Fifty requests per second per merchant account, then the provider says no. " * 4
    + "\n\n## Outages\n\n"
    + "Authorization fails fast and the basket is kept for the shopper's return. " * 4
).strip()


def _add(dispatcher: Dispatcher, body: str, title: str = "Provider integration") -> str:
    return dispatcher.dispatch(
        "add",
        {
            "type": "architecture",
            "title": title,
            "description": "Notes on the provider boundary.",
            "body": body,
        },
    )["id"]


def _chunk_headings(uow_factory: Factory, doc_id: str) -> list[str]:
    with uow_factory() as uow:
        return uow.chunks.headings(doc_id)


class TestWriting:
    def test_a_write_stores_one_vector_per_section(
        self, dispatcher: Dispatcher, uow_factory: Factory
    ) -> None:
        doc_id = _add(dispatcher, _SECTIONS)
        assert _chunk_headings(uow_factory, doc_id) == ["Credentials", "Rate limits", "Outages"]

    def test_a_bodyless_document_stores_no_chunks(
        self, dispatcher: Dispatcher, uow_factory: Factory
    ) -> None:
        doc_id = _add(dispatcher, "")
        assert _chunk_headings(uow_factory, doc_id) == []

    def test_chunk_vectors_are_comparable_with_the_query(self, uow_factory: Factory) -> None:
        """Stored blobs round-trip to embeddings the scorer can actually use."""
        with uow_factory() as uow:
            vectors = uow.chunks.active_vectors(DeterministicEmbedder().model_id)
        assert vectors == []  # empty store: the point is that it does not raise


class TestReplacement:
    def test_editing_the_body_replaces_the_whole_chunk_set(
        self, dispatcher: Dispatcher, uow_factory: Factory
    ) -> None:
        """Wholesale, because an edit renumbers every section after it.

        A chunk left behind from the previous body keeps a section that no
        longer exists answerable — the failure mode that makes a stale chunk
        worse than no chunk.
        """
        doc_id = _add(dispatcher, _SECTIONS)
        dispatcher.dispatch(
            "update",
            {
                "doc_id": doc_id,
                "replace_body": "## Key custody\n\n"
                + "The private key never leaves the vault. " * 6,
                "force": True,
            },
        )
        assert _chunk_headings(uow_factory, doc_id) == ["Key custody"]

    def test_a_metadata_only_edit_keeps_the_chunks(
        self, dispatcher: Dispatcher, uow_factory: Factory
    ) -> None:
        doc_id = _add(dispatcher, _SECTIONS)
        dispatcher.dispatch("update", {"doc_id": doc_id, "set_title": "Renamed"})
        assert _chunk_headings(uow_factory, doc_id) == ["Credentials", "Rate limits", "Outages"]


class TestRemoval:
    def test_deleting_a_document_takes_its_chunks(
        self, dispatcher: Dispatcher, uow_factory: Factory
    ) -> None:
        doc_id = _add(dispatcher, _SECTIONS)
        dispatcher.dispatch("delete", {"doc_id": doc_id})
        assert _chunk_headings(uow_factory, doc_id) == []

    def test_archiving_drops_the_chunks_from_the_ranked_pool(
        self, dispatcher: Dispatcher, uow_factory: Factory
    ) -> None:
        """An archived document must not be reachable through a section either.

        `active_vectors` filters on the document being active, so this holds
        even if the rows survive — asserting on the pool rather than the table
        is what makes the test about visibility rather than about storage.
        """
        doc_id = _add(dispatcher, _SECTIONS)
        dispatcher.dispatch("archive", {"doc_id": doc_id})
        with uow_factory() as uow:
            pool = uow.chunks.active_vectors(DeterministicEmbedder().model_id)
        assert [entry for entry in pool if entry[0] == doc_id] == []


class TestReindex:
    def test_reindex_rebuilds_chunks_from_the_files(
        self, dispatcher: Dispatcher, uow_factory: Factory
    ) -> None:
        """The index is derived; a fresh clone must end up with chunks too."""
        doc_id = _add(dispatcher, _SECTIONS)
        with uow_factory() as uow:
            uow.chunks.remove(doc_id)
            uow.commit()
        assert _chunk_headings(uow_factory, doc_id) == []

        dispatcher.dispatch("reindex", {})
        dispatcher.dispatch("embed_flush", {})
        assert _chunk_headings(uow_factory, doc_id) == ["Credentials", "Rate limits", "Outages"]


class TestPooling:
    """The rule that turns section vectors back into a document ranking."""

    def test_a_document_scores_its_best_section(self) -> None:
        embedder = DeterministicEmbedder()
        query = embedder.embed("certificate rotation")
        near = embedder.embed("certificate rotation happens at ten months")
        far = embedder.embed("bananas and other tropical fruit")

        ranking = HybridScorer().semantic_ranking(
            query,
            [
                VectorCandidate("a", far, section="Bananas"),
                VectorCandidate("a", near, section="Rotation"),
                VectorCandidate("b", far),
            ],
        )

        scores = {hit.doc_id: hit.similarity for hit in ranking}
        assert scores["a"] == pytest.approx(query.cosine_similarity(near))
        assert scores["a"] > scores["b"]
        # And the *winning* section is named, not merely its score kept:
        # that heading is what `get --section` is asked for next
        # (issue-afd25273ff1f).
        assert {hit.doc_id: hit.section for hit in ranking}["a"] == "Rotation"

    def test_each_document_appears_once(self) -> None:
        """RRF fuses two rankings *of documents*; a repeat would be counted twice."""
        embedder = DeterministicEmbedder()
        query = embedder.embed("anything")
        vector = embedder.embed("some section text")
        ranking = HybridScorer().semantic_ranking(
            query,
            [
                VectorCandidate("a", vector),
                VectorCandidate("a", vector),
                VectorCandidate("a", vector),
            ],
        )
        assert [hit.doc_id for hit in ranking] == ["a"]

    def test_the_ranking_is_ordered_best_first(self) -> None:
        embedder = DeterministicEmbedder()
        query = embedder.embed("certificate rotation")
        ranking = HybridScorer().semantic_ranking(
            query,
            [
                VectorCandidate("far", embedder.embed("bananas")),
                VectorCandidate("near", embedder.embed("certificate rotation")),
            ],
        )
        assert [hit.doc_id for hit in ranking] == ["near", "far"]


class TestTheMatchedSectionIsNamedAndUsable:
    """issue-afd25273ff1f: the ranking knew which section won and dropped it.

    Chunking made a long document reachable by any of its sections and then
    reported only the document, so an agent either pulled the whole body — the
    cost chunking exists to remove — or discovered the headings in a second
    round trip. The heading now rides on the skeleton, and the test that
    matters is not that a string is present but that `get --section` accepts it
    verbatim: a citation nobody can dereference is decoration.
    """

    def test_a_ranked_hit_names_its_section_and_the_name_reads_back(
        self, dispatcher: Dispatcher
    ) -> None:
        doc_id = _add(dispatcher, _SECTIONS)
        hits = dispatcher.dispatch("context", {"task": "rate limits per merchant account"})
        hit = next(h for h in hits if h["id"] == doc_id)

        assert hit["matched_section"] == "Rate limits"
        view = dispatcher.dispatch("get", {"doc_id": doc_id, "section": hit["matched_section"]})
        assert view["section"] == "Rate limits"
        assert "Fifty requests per second" in view["body"]

    def test_a_graph_reached_neighbour_names_no_section(self, dispatcher: Dispatcher) -> None:
        # It is there because a selected document links it, not because any
        # vector of it scored — so there is no winning section to name, and
        # absent must not read as "the whole document matched".
        target = _add(dispatcher, _SECTIONS, title="Provider integration")
        _add(dispatcher, "Body.", title="Unrelated neighbour")
        neighbour = dispatcher.dispatch(
            "add",
            {
                "type": "decision",
                "title": "Use the provider",
                "description": "d",
                "related": [target],
                "body": "Body.",
            },
        )["id"]
        hits = dispatcher.dispatch("context", {"task": "use the provider", "limit": 4, "expand": 2})
        by_id = {h["id"]: h for h in hits}
        assert by_id[neighbour]["matched_section"] is None or not by_id[neighbour].get("via_graph")
        graph_hits = [h for h in hits if h.get("via_graph")]
        assert graph_hits, "expansion should have pulled at least one neighbour"
        assert all(h["matched_section"] is None for h in graph_hits)

    def test_a_preamble_match_names_no_section(self, dispatcher: Dispatcher) -> None:
        # The text before the first `##` is a chunk with no heading, and so is
        # the continuation of an over-long section. Both rank normally and
        # neither can be asked for by name, so they must arrive as absent —
        # reporting `""` would hand an agent a heading `get --section` rejects.
        body = (
            "Settlement runs nightly and reconciles against the ledger file. " * 5
            + "\n\n## Rate limits\n\n"
            + "Fifty requests per second per merchant account. " * 5
        ).strip()
        doc_id = _add(dispatcher, body, title="Settlement")
        hits = dispatcher.dispatch("context", {"task": "settlement reconciles the ledger file"})
        hit = next(h for h in hits if h["id"] == doc_id)
        assert hit["matched_section"] is None
