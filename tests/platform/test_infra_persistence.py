"""Integration tests for the SQLAlchemy repositories against real SQLite."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.value_objects.queries import DocumentFilter
from docir.modules.documents.domain.value_objects.relations import RelatedRef
from docir.modules.tags.domain.entities.tag import Tag
from docir.platform.embedding.vector import Embedding
from docir.platform.persistence.repositories import count_documents
from docir.platform.persistence.sqlalchemy_uow import SqlAlchemyUnitOfWork
from docir.platform.persistence.unit_of_work import UnitOfWork

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
            uow.documents.save(_doc("adr-0001", tags=("auth",), related=(RelatedRef("adr-0002"),)))
            uow.commit()
        with uow_factory() as uow:
            doc = uow.documents.get("adr-0001")
            assert doc is not None
            assert doc.tags == ("auth",)
            assert doc.related == (RelatedRef("adr-0002"),)
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
            uow.documents.save(_doc("adr-0001", related=(RelatedRef("adr-0002", "supersedes"),)))
            uow.commit()
        with uow_factory() as uow:
            assert uow.documents.outgoing("adr-0001") == ["adr-0002"]
            assert uow.documents.incoming("adr-0002") == ["adr-0001"]
            # The typed edge kind round-trips through the relations table.
            assert uow.documents.get("adr-0001").related == (RelatedRef("adr-0002", "supersedes"),)
            rels = uow.documents.relations()
            assert (rels[0].source, rels[0].target, rels[0].kind) == (
                "adr-0001",
                "adr-0002",
                "supersedes",
            )

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

    def test_usage_counts_only_for_keys_asked_about(self, uow_factory: Factory) -> None:
        with uow_factory() as uow:
            for key in ("auth", "cache", "dead"):
                uow.tags.save(Tag(key, "d"))
            uow.documents.save(_doc("adr-0001", tags=("auth", "cache")))
            uow.documents.save(_doc("adr-0002", tags=("auth",)))
            uow.commit()
        with uow_factory() as uow:
            counts = uow.tags.usage_counts(["auth", "cache", "dead"])
            # A key nobody uses is absent, not 0 — the caller supplies the zero,
            # so "not asked about" and "used by nothing" stay distinguishable.
            assert counts == {"auth": 2, "cache": 1}
            assert uow.tags.usage_counts(["cache"]) == {"cache": 1}
            assert uow.tags.usage_counts([]) == {}

    def test_usage_counts_include_archived(self, uow_factory: Factory) -> None:
        # `tag rm` blocks on archived documents too, so a count that skipped
        # them would report a tag as dead that then refuses to be removed.
        with uow_factory() as uow:
            uow.tags.save(Tag("auth", "d"))
            uow.documents.save(_doc("adr-0001", tags=("auth",), archived=True))
            uow.commit()
        with uow_factory() as uow:
            assert uow.tags.usage_counts(["auth"]) == {"auth": 1}


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


_MODEL = "test-model-v1"


class TestEmbeddingRepository:
    def test_dirty_and_vector_lifecycle(self, uow_factory: Factory) -> None:
        with uow_factory() as uow:
            uow.documents.save(_doc("adr-0001"))
            uow.embeddings.mark_dirty("adr-0001")
            uow.commit()
        with uow_factory() as uow:
            assert uow.embeddings.dirty_ids(_MODEL) == ["adr-0001"]
            uow.embeddings.set_vector("adr-0001", Embedding((1.0, 0.0)), _MODEL)
            uow.commit()
        with uow_factory() as uow:
            assert uow.embeddings.dirty_ids(_MODEL) == []
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
            uow.embeddings.set_vector("adr-0001", Embedding((1.0, 0.0)), _MODEL)
            uow.embeddings.set_vector("adr-0002", Embedding((0.0, 1.0)), _MODEL)
            uow.commit()
        with uow_factory() as uow:
            ids = [doc_id for doc_id, _vec in uow.embeddings.active_vectors(_MODEL)]
            assert ids == ["adr-0001"]

    def test_vectors_from_another_model_are_recomputed_not_compared(
        self, uow_factory: Factory
    ) -> None:
        # Changing embedder changes the vector space, and often its width, so a
        # stale vector cannot be reused. It must fall out of ranking and come
        # back as dirty. Without this, flipping the default embedder made
        # `docir context` raise "dimension mismatch" in every existing store.
        with uow_factory() as uow:
            uow.documents.save(_doc("adr-0001"))
            uow.embeddings.set_vector("adr-0001", Embedding((1.0, 0.0)), "old-model")
            uow.commit()
        with uow_factory() as uow:
            assert uow.embeddings.active_vectors("new-model") == []
            assert uow.embeddings.dirty_ids("new-model") == ["adr-0001"]
            # ...and the old model still sees its own vector.
            assert [i for i, _ in uow.embeddings.active_vectors("old-model")] == ["adr-0001"]

    def test_rollback_on_error(self, uow_factory: Factory) -> None:
        try:
            with uow_factory() as uow:
                uow.documents.save(_doc("adr-0001"))
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        with uow_factory() as uow:
            assert uow.documents.get("adr-0001") is None
