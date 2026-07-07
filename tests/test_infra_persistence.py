"""Integration tests for the SQLAlchemy repositories against real SQLite."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from docir.domain.entities.document import Document
from docir.domain.entities.tag import Tag
from docir.domain.ports.unit_of_work import UnitOfWork
from docir.domain.value_objects.embedding import Embedding
from docir.domain.value_objects.queries import DocumentFilter
from docir.infrastructure.persistence.repositories import count_documents
from docir.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

Factory = Callable[[], UnitOfWork]


def _doc(doc_id: str, **kw: object) -> Document:
    defaults: dict[str, object] = {
        "title": "Title",
        "description": "Desc",
        "type": "decision",
        "status": "proposed",
        "created": date(2026, 1, 1),
        "updated": date(2026, 1, 1),
        "body": "body text",
    }
    defaults.update(kw)
    return Document(id=doc_id, **defaults)  # type: ignore[arg-type]


class TestDocumentRepository:
    def test_next_number_increments_and_persists(self, uow_factory: Factory) -> None:
        with uow_factory() as uow:
            assert uow.documents.next_number("adr") == 1
            assert uow.documents.next_number("adr") == 2
            uow.commit()
        with uow_factory() as uow:
            assert uow.documents.next_number("adr") == 3

    def test_save_get_with_tags_and_relations(self, uow_factory: Factory) -> None:
        with uow_factory() as uow:
            uow.documents.save(_doc("adr-0002"))
            uow.documents.save(_doc("adr-0001", tags=("auth",), related=("adr-0002",)))
            uow.commit()
        with uow_factory() as uow:
            doc = uow.documents.get("adr-0001")
            assert doc is not None
            assert doc.tags == ("auth",)
            assert doc.related == ("adr-0002",)
            assert uow.documents.exists("adr-0001")
            assert not uow.documents.exists("nope")
            assert uow.documents.get("nope") is None

    def test_save_replaces_tags_and_relations(self, uow_factory: Factory) -> None:
        with uow_factory() as uow:
            uow.documents.save(_doc("adr-0001", tags=("auth", "api")))
            uow.commit()
        with uow_factory() as uow:
            uow.documents.save(_doc("adr-0001", tags=("storage",)))
            uow.commit()
        with uow_factory() as uow:
            assert uow.documents.get("adr-0001").tags == ("storage",)

    def test_relations_graph(self, uow_factory: Factory) -> None:
        with uow_factory() as uow:
            uow.documents.save(_doc("adr-0002"))
            uow.documents.save(_doc("adr-0001", related=("adr-0002",)))
            uow.commit()
        with uow_factory() as uow:
            assert uow.documents.outgoing("adr-0001") == ["adr-0002"]
            assert uow.documents.incoming("adr-0002") == ["adr-0001"]
            rels = uow.documents.relations()
            assert (rels[0].source, rels[0].target) == ("adr-0001", "adr-0002")

    def test_delete_cascades(self, uow_factory: Factory) -> None:
        with uow_factory() as uow:
            uow.documents.save(_doc("adr-0001", tags=("auth",)))
            uow.embeddings.mark_dirty("adr-0001")
            uow.commit()
        with uow_factory() as uow:
            uow.documents.delete("adr-0001")
            uow.commit()
        with uow_factory() as uow:
            assert uow.documents.get("adr-0001") is None
            assert uow.embeddings.get_vector("adr-0001") is None

    def test_query_filters(self, uow_factory: Factory) -> None:
        with uow_factory() as uow:
            uow.documents.save(_doc("adr-0001", tags=("auth",), status="accepted"))
            uow.documents.save(_doc("issue-0001", type="issue", status="resolved"))
            uow.documents.save(_doc("adr-0002", archived=True))
            uow.commit()
        with uow_factory() as uow:
            by_type = uow.documents.query(DocumentFilter(types=("decision",)))
            assert {d.id for d in by_type} == {"adr-0001"}  # adr-0002 archived
            by_tag = uow.documents.query(DocumentFilter(tags=("auth",)))
            assert {d.id for d in by_tag} == {"adr-0001"}
            with_archived = uow.documents.query(
                DocumentFilter(types=("decision",), include_archived=True)
            )
            assert {d.id for d in with_archived} == {"adr-0001", "adr-0002"}
            active = uow.documents.query(DocumentFilter(inactive_statuses=("resolved",)))
            assert "issue-0001" not in {d.id for d in active}
            inactive = uow.documents.query(
                DocumentFilter(inactive_statuses=("resolved",), include_inactive=True)
            )
            assert "issue-0001" in {d.id for d in inactive}

    def test_all_and_count(self, uow_factory: Factory) -> None:
        with uow_factory() as uow:
            uow.documents.save(_doc("adr-0001"))
            uow.documents.save(_doc("adr-0002"))
            uow.commit()
        with uow_factory() as uow:
            assert len(uow.documents.all()) == 2
        factory_uow = uow_factory()
        assert isinstance(factory_uow, SqlAlchemyUnitOfWork)
        with factory_uow as uow:
            assert count_documents(uow._session) == 2  # type: ignore[attr-defined]


class TestTagRepository:
    def test_crud(self, uow_factory: Factory) -> None:
        with uow_factory() as uow:
            uow.tags.save(Tag("auth", "Auth."))
            uow.tags.save(Tag("auth", "Updated."))  # upsert
            uow.commit()
        with uow_factory() as uow:
            assert uow.tags.exists("auth")
            assert uow.tags.get("auth").description == "Updated."
            assert uow.tags.get("nope") is None
            assert [t.key for t in uow.tags.all()] == ["auth"]
            uow.tags.delete("auth")
            uow.commit()
        with uow_factory() as uow:
            assert not uow.tags.exists("auth")


class TestSearchIndex:
    def test_index_search_remove(self, uow_factory: Factory) -> None:
        with uow_factory() as uow:
            doc = _doc("adr-0001", title="Authentication", body="tokens and sessions")
            uow.documents.save(doc)
            uow.search.index(doc)
            uow.commit()
        with uow_factory() as uow:
            hits = uow.search.search("authentication", limit=5)
            assert hits and hits[0].doc_id == "adr-0001"
            assert uow.search.search("", limit=5) == []
        with uow_factory() as uow:
            uow.search.remove("adr-0001")
            uow.commit()
        with uow_factory() as uow:
            assert uow.search.search("authentication", limit=5) == []


class TestEmbeddingRepository:
    def test_dirty_and_vector_lifecycle(self, uow_factory: Factory) -> None:
        with uow_factory() as uow:
            uow.documents.save(_doc("adr-0001"))
            uow.embeddings.mark_dirty("adr-0001")
            uow.commit()
        with uow_factory() as uow:
            assert uow.embeddings.dirty_ids() == ["adr-0001"]
            uow.embeddings.set_vector("adr-0001", Embedding((1.0, 0.0)))
            uow.commit()
        with uow_factory() as uow:
            assert uow.embeddings.dirty_ids() == []
            assert uow.embeddings.get_vector("adr-0001") is not None
            uow.embeddings.clear_dirty("adr-0001")
            uow.embeddings.remove("adr-0001")
            uow.commit()
        with uow_factory() as uow:
            assert uow.embeddings.get_vector("adr-0001") is None

    def test_active_vectors_excludes_archived(self, uow_factory: Factory) -> None:
        with uow_factory() as uow:
            uow.documents.save(_doc("adr-0001"))
            uow.documents.save(_doc("adr-0002", archived=True))
            uow.embeddings.set_vector("adr-0001", Embedding((1.0, 0.0)))
            uow.embeddings.set_vector("adr-0002", Embedding((0.0, 1.0)))
            uow.commit()
        with uow_factory() as uow:
            ids = [doc_id for doc_id, _vec in uow.embeddings.active_vectors()]
            assert ids == ["adr-0001"]

    def test_rollback_on_error(self, uow_factory: Factory) -> None:
        try:
            with uow_factory() as uow:
                uow.documents.save(_doc("adr-0001"))
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        with uow_factory() as uow:
            assert uow.documents.get("adr-0001") is None
