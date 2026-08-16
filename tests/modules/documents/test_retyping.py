"""Retyping a document: ``docir update <id> --type`` (adr-f8cce745d0d5).

A document's type used to be fixed at creation, so renaming a corpus's
vocabulary meant hand-editing the markdown the write path exists to own
(issue-4952ce77d19d). These tests pin what a retype must and must not touch:
the id and its prefix stay, the file moves, the status is checked against the
type being *entered*, and none of it depends on the type being left still
existing.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from docir.config.settings import Settings
from docir.entry_points.composition import Container, build_container
from docir.entry_points.dispatch import Dispatcher
from docir.platform.errors import (
    DisallowedRelationError,
    InvalidStatusError,
    UnknownDocumentTypeError,
)

#: Two types over the frozen core. `product_decision` deliberately does NOT
#: declare `proposed`/`accepted`, so carrying a core `decision` into it is the
#: interesting case rather than the trivial one. `note` shares no status with
#: either and whitelists its relations, which `decision` does not.
SCHEMA = """\
profiles: [software]

types:
  product_decision:
    prefix: pdr
    level: 3
    default_status: draft
    statuses:
      draft: [active]
      active: [retired]
      retired: []

  note:
    prefix: note
    level: 1
    default_status: draft
    allowed_relations:
      refines: [architecture]
    statuses:
      draft: [active]
      active: []
"""

#: The same schema with the core `decision` subtracted and its `adr` prefix
#: claimed by `product_decision` — the migration issue-ab138501abfd describes.
RENAMED_SCHEMA = """\
profiles: [software]
disable_types: [decision]

types:
  product_decision:
    prefix: adr
    level: 3
    default_status: draft
    statuses:
      draft: [active]
      active: [retired]
      retired: []
"""


def _container(settings: Settings, schema: str) -> Container:
    settings.ensure_directories()
    settings.schema_path.write_text(schema, encoding="utf-8")
    return build_container(settings, background_embeddings=False)


@pytest.fixture
def docs(settings: Settings) -> Iterator[Dispatcher]:
    container = _container(settings, SCHEMA)
    try:
        yield container.dispatcher
    finally:
        container.close()


def _add(docs: Dispatcher, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "type": "decision",
        "title": "Use Postgres",
        "description": "Why the store is Postgres.",
        "body": "## Context\n\nWe need a database.\n",
    }
    payload.update(overrides)
    return docs.dispatch("add", payload)


class TestTheIdSurvives:
    def test_the_id_and_its_prefix_are_untouched(self, docs: Dispatcher) -> None:
        # The id is the corpus's only address -- every `related` edge that
        # points here spells it out -- so it cannot be re-minted to match the
        # new type's prefix. A prefix records which type minted an id.
        created = _add(docs)
        retyped = docs.dispatch(
            "update",
            {"doc_id": created["id"], "set_type": "product_decision", "status": "active"},
        )
        assert retyped["id"] == created["id"] == "adr-0001"
        assert retyped["type"] == "product_decision"

    def test_incoming_edges_still_resolve(self, docs: Dispatcher) -> None:
        target = _add(docs)
        source = _add(docs, title="Sharding", related=[target["id"]])
        docs.dispatch(
            "update",
            {"doc_id": target["id"], "set_type": "product_decision", "status": "active"},
        )
        edges = docs.dispatch("get", {"doc_id": source["id"]})["related"]
        assert [ref["target"] for ref in edges] == [target["id"]]


class TestTheFileMoves:
    def test_it_lands_in_the_new_type_directory(self, docs: Dispatcher, settings: Settings) -> None:
        created = _add(docs)
        old_path = settings.docs_root / created["path"]
        assert old_path.exists()

        retyped = docs.dispatch(
            "update",
            {"doc_id": created["id"], "set_type": "product_decision", "status": "active"},
        )

        assert retyped["path"] == "product_decisions/adr-0001-use-postgres.md"
        assert (settings.docs_root / retyped["path"]).exists()
        assert not old_path.exists()

    def test_the_filename_carries_over_unchanged(self, docs: Dispatcher) -> None:
        # A retype is not a retitle. Reslugging here would bury the directory
        # move inside a rename git cannot follow.
        created = _add(docs)
        docs.dispatch("update", {"doc_id": created["id"], "set_title": "Something else entirely"})
        retyped = docs.dispatch(
            "update",
            {"doc_id": created["id"], "set_type": "product_decision", "status": "active"},
        )
        assert retyped["path"].endswith("/adr-0001-use-postgres.md")

    def test_the_vacated_directory_is_dropped(self, docs: Dispatcher, settings: Settings) -> None:
        # A directory listing is how a person reads which types a store uses.
        created = _add(docs)
        docs.dispatch(
            "update",
            {"doc_id": created["id"], "set_type": "product_decision", "status": "active"},
        )
        assert not (settings.docs_root / "decisions").exists()

    def test_a_directory_still_holding_documents_is_kept(
        self, docs: Dispatcher, settings: Settings
    ) -> None:
        created = _add(docs)
        _add(docs, title="Stays put")
        docs.dispatch(
            "update",
            {"doc_id": created["id"], "set_type": "product_decision", "status": "active"},
        )
        assert (settings.docs_root / "decisions").is_dir()

    def test_the_body_survives_the_move(self, docs: Dispatcher) -> None:
        created = _add(docs)
        docs.dispatch(
            "update",
            {"doc_id": created["id"], "set_type": "product_decision", "status": "active"},
        )
        assert "We need a database." in docs.dispatch("get", {"doc_id": created["id"]})["body"]


class TestStatusIsCheckedAgainstTheTypeBeingEntered:
    def test_a_shared_status_carries_over_untouched(self, docs: Dispatcher) -> None:
        created = _add(docs, type="issue")  # `open`, which `note` does not declare
        docs.dispatch("update", {"doc_id": created["id"], "status": "resolved"})
        # `note` declares neither, so use one it does: draft -> both declare it.
        drafted = _add(docs, type="release_note")  # starts `draft`
        retyped = docs.dispatch("update", {"doc_id": drafted["id"], "set_type": "note"})
        assert retyped["status"] == "draft"

    def test_a_status_the_new_type_lacks_is_refused(self, docs: Dispatcher) -> None:
        created = _add(docs)  # `proposed`, absent from `product_decision`
        with pytest.raises(InvalidStatusError) as excinfo:
            docs.dispatch("update", {"doc_id": created["id"], "set_type": "product_decision"})
        message = str(excinfo.value)
        assert "--status" in message  # says how to proceed
        assert "draft, active, retired" in message  # names what would work

    def test_it_is_never_silently_reset_to_the_default(self, docs: Dispatcher) -> None:
        # The rejected alternative: falling back to `default_status` rewrites
        # every `accepted` in a corpus to `draft` and reports success.
        created = _add(docs)
        docs.dispatch("update", {"doc_id": created["id"], "status": "accepted"})
        with pytest.raises(InvalidStatusError):
            docs.dispatch("update", {"doc_id": created["id"], "set_type": "product_decision"})
        assert docs.dispatch("get", {"doc_id": created["id"]})["status"] == "accepted"

    def test_a_retype_is_membership_not_a_transition(self, docs: Dispatcher) -> None:
        # `retired` is unreachable from `draft` in one step, but the document is
        # not transitioning -- it is arriving. The old type's graph has no say
        # over the new type's, and neither does the new type's own graph about a
        # status the document is being given on entry.
        created = _add(docs)
        retyped = docs.dispatch(
            "update",
            {"doc_id": created["id"], "set_type": "product_decision", "status": "retired"},
        )
        assert retyped["status"] == "retired"

    def test_a_status_no_type_declares_is_still_refused(self, docs: Dispatcher) -> None:
        created = _add(docs)
        with pytest.raises(InvalidStatusError):
            docs.dispatch(
                "update",
                {"doc_id": created["id"], "set_type": "product_decision", "status": "invented"},
            )

    def test_override_does_not_report_a_forced_transition(self, docs: Dispatcher) -> None:
        # There is no edge between two types' status graphs to break, so
        # `--override` has nothing to override and must not warn.
        created = _add(docs)
        retyped = docs.dispatch(
            "update",
            {
                "doc_id": created["id"],
                "set_type": "product_decision",
                "status": "retired",
                "allow_transition_override": True,
            },
        )
        assert retyped["forced_transition"] is None


class TestTheEdgesAreRecheckedAgainstTheNewType:
    def test_an_edge_the_new_type_forbids_blocks_the_retype(self, docs: Dispatcher) -> None:
        # `allowed_relations` is a property of the SOURCE type, so a retype can
        # carry a document under a whitelist its untouched edges fail. They are
        # validated even though this call did not supply them, because this is
        # the write that would persist them.
        other = _add(docs, title="Other")
        source = _add(docs, title="Linked", related=[other["id"]])
        with pytest.raises(DisallowedRelationError):
            docs.dispatch("update", {"doc_id": source["id"], "set_type": "note", "status": "draft"})

    def test_a_permitted_edge_survives(self, docs: Dispatcher) -> None:
        arch = _add(docs, type="architecture", title="Shape")
        source = _add(docs, title="Linked", related=[f"{arch['id']}:refines"])
        retyped = docs.dispatch(
            "update", {"doc_id": source["id"], "set_type": "note", "status": "draft"}
        )
        assert [ref["target"] for ref in retyped["related"]] == [arch["id"]]

    def test_edges_supplied_in_the_same_call_use_the_new_type_too(self, docs: Dispatcher) -> None:
        other = _add(docs, title="Other")
        source = _add(docs, title="Linked")
        with pytest.raises(DisallowedRelationError):
            docs.dispatch(
                "update",
                {
                    "doc_id": source["id"],
                    "set_type": "note",
                    "status": "draft",
                    "set_related": [other["id"]],
                },
            )


class TestDegenerateCases:
    def test_an_unknown_target_type_is_refused_naming_the_real_ones(self, docs: Dispatcher) -> None:
        created = _add(docs)
        with pytest.raises(UnknownDocumentTypeError) as excinfo:
            docs.dispatch("update", {"doc_id": created["id"], "set_type": "prodcut_decision"})
        assert "product_decision" in str(excinfo.value)

    def test_retyping_to_the_current_type_changes_nothing(
        self, docs: Dispatcher, settings: Settings
    ) -> None:
        created = _add(docs)
        retyped = docs.dispatch("update", {"doc_id": created["id"], "set_type": "decision"})
        assert retyped["path"] == created["path"]
        assert (settings.docs_root / created["path"]).exists()
        assert retyped["updated"] == created["updated"]


class TestLeavingATypeTheSchemaNoLongerDeclares:
    """The load-bearing case: the two halves of adr-f8cce745d0d5 must not deadlock.

    Declaring the replacement type first is impossible while the old one holds
    the prefix; disabling the old one first strands the corpus on a type the
    schema does not know. If a retype needed a *known* source type, the only way
    through would be the hand-editing both changes exist to remove.
    """

    def test_a_document_can_be_retyped_out_of_a_disabled_type(self, settings: Settings) -> None:
        container = _container(settings, SCHEMA)
        try:
            created = _add(container.dispatcher)
            doc_id = created["id"]
        finally:
            container.close()

        # The schema edit lands: `decision` is gone and `product_decision` now
        # claims `adr`, the prefix this document's id already carries.
        container = _container(settings, RENAMED_SCHEMA)
        try:
            docs = container.dispatcher
            with pytest.raises(UnknownDocumentTypeError):
                _add(docs, title="A new one")  # the old name is gone for good

            retyped = docs.dispatch(
                "update",
                {"doc_id": doc_id, "set_type": "product_decision", "status": "active"},
            )
            assert retyped["type"] == "product_decision"
            assert retyped["id"] == doc_id  # still adr-0001
            assert retyped["path"] == "product_decisions/adr-0001-use-postgres.md"
        finally:
            container.close()

    def test_the_freed_prefix_keeps_minting_past_the_existing_ids(self, settings: Settings) -> None:
        container = _container(settings, SCHEMA)
        try:
            _add(container.dispatcher)  # adr-0001
        finally:
            container.close()

        container = _container(settings, RENAMED_SCHEMA)
        try:
            docs = container.dispatcher
            docs.dispatch(
                "update",
                {"doc_id": "adr-0001", "set_type": "product_decision", "status": "active"},
            )
            minted = _add(docs, type="product_decision", title="The next one")
            assert minted["id"] == "adr-0002"
        finally:
            container.close()

    def test_check_reports_the_stranded_documents_until_they_are_retyped(
        self, settings: Settings
    ) -> None:
        container = _container(settings, SCHEMA)
        try:
            _add(container.dispatcher)
        finally:
            container.close()

        container = _container(settings, RENAMED_SCHEMA)
        try:
            docs = container.dispatcher
            kinds = [issue["kind"] for issue in docs.dispatch("check", {})]
            assert "unknown-type" in kinds

            docs.dispatch(
                "update",
                {"doc_id": "adr-0001", "set_type": "product_decision", "status": "active"},
            )
            after = [issue["kind"] for issue in docs.dispatch("check", {})]
            assert "unknown-type" not in after
        finally:
            container.close()
