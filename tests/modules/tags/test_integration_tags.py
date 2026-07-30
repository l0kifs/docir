"""Integration tests for the tag-registry use cases."""

from __future__ import annotations

import pytest

from docir.config.settings import Settings
from docir.entry_points.dispatch import Dispatcher
from docir.modules.tags.domain.entities.tag import Tag
from docir.platform.errors import (
    TagAlreadyExistsError,
    TagInUseError,
    TagNotFoundError,
    ValidationError,
)


def test_add_and_list(dispatcher: Dispatcher, settings: Settings) -> None:
    dispatcher.dispatch("tag_add", {"key": "auth", "description": "Auth."})
    dispatcher.dispatch("tag_add", {"key": "api", "description": "API."})
    tags = dispatcher.dispatch("tag_list", {})
    assert {t["key"] for t in tags} == {"auth", "api"}
    assert settings.tags_path.exists()


def _register_legacy_key(uow_factory: object, key: str) -> None:
    """Put a key in the registry the way one predating the rule got there.

    Straight through the unit of work: `tag add` now refuses it, which is the
    point — the only keys that can fail the grammar are ones written before it
    existed or edited into `tags.yaml` by hand.
    """
    with uow_factory() as uow:  # type: ignore[operator]
        uow.tags.save(Tag(key=key, description="Predates the format rule."))
        uow.commit()


class TestKeyFormat:
    """GAP-027: any non-empty string was a valid key, so `auth`, `Auth` and
    `authentication` could all exist and nothing objected."""

    @pytest.mark.parametrize("key", ["Auth", "AUTH", "auth key", "auth_key", "9lives", "-auth", ""])
    def test_a_key_outside_the_grammar_is_rejected(self, dispatcher: Dispatcher, key: str) -> None:
        with pytest.raises(ValidationError):
            dispatcher.dispatch("tag_add", {"key": key, "description": "d"})

    @pytest.mark.parametrize("key", ["auth", "auth-n", "a", "oauth2", "x-9"])
    def test_a_key_inside_the_grammar_is_accepted(self, dispatcher: Dispatcher, key: str) -> None:
        assert dispatcher.dispatch("tag_add", {"key": key, "description": "d"})["key"] == key

    def test_rename_validates_the_new_key(self, dispatcher: Dispatcher) -> None:
        dispatcher.dispatch("tag_add", {"key": "auth", "description": "d"})
        with pytest.raises(ValidationError):
            dispatcher.dispatch("tag_rename", {"old": "auth", "new": "Auth"})

    def test_renaming_away_from_a_legacy_key_is_the_migration_path(
        self, dispatcher: Dispatcher, uow_factory: object
    ) -> None:
        # A key that predates the rule can only be fixed by renaming it, so
        # `rename` must validate the NEW key and leave the old one alone.
        _register_legacy_key(uow_factory, "Auth")
        assert dispatcher.dispatch("tag_rename", {"old": "Auth", "new": "auth"}) is not None
        assert {t["key"] for t in dispatcher.dispatch("tag_list", {})} == {"auth"}

    def test_check_warns_about_a_legacy_key_without_failing_strict(
        self, dispatcher: Dispatcher, uow_factory: object
    ) -> None:
        # A corpus written before the rule must not start failing CI for
        # something its author could not have avoided.
        _register_legacy_key(uow_factory, "Auth")
        findings = dispatcher.dispatch("check", {})
        offending = [f for f in findings if f["kind"] == "tag-key-format"]
        assert len(offending) == 1
        assert "'Auth'" in offending[0]["message"]
        assert offending[0]["severity"] == "warning"
        # A registry finding, not a document one — the key is in the message.
        assert not offending[0]["doc_ids"]
        # What `--strict` actually gates on: no error-severity finding.
        assert [f for f in findings if f["severity"] == "error"] == []

    def test_a_conforming_registry_produces_no_finding(self, dispatcher: Dispatcher) -> None:
        # A count alone cannot tell "nothing is wrong" from "nothing is checked".
        dispatcher.dispatch("tag_add", {"key": "auth", "description": "d"})
        findings = dispatcher.dispatch("check", {})
        assert [f for f in findings if f["kind"] == "tag-key-format"] == []


class TestUsageCounts:
    """A registry that can only grow: nothing said which tags were dead."""

    def test_list_reports_documents_per_tag(self, dispatcher: Dispatcher) -> None:
        _two_tags_and_three_docs(dispatcher)
        usage = {t["key"]: t["usage"] for t in dispatcher.dispatch("tag_list", {})}
        assert usage == {"auth": 2, "authn": 1}

    def test_a_tag_no_document_carries_reports_zero(self, dispatcher: Dispatcher) -> None:
        # The whole point: a dead tag must be visible as 0, not absent.
        dispatcher.dispatch("tag_add", {"key": "dead", "description": "Nobody uses this."})
        assert dispatcher.dispatch("tag_list", {})[0]["usage"] == 0

    def test_zero_means_remove_needs_no_force(self, dispatcher: Dispatcher) -> None:
        # The count is only useful if it predicts what `tag rm` will do.
        _two_tags_and_three_docs(dispatcher)
        dispatcher.dispatch("tag_add", {"key": "dead", "description": "d"})
        usage = {t["key"]: t["usage"] for t in dispatcher.dispatch("tag_list", {})}
        assert usage["dead"] == 0
        dispatcher.dispatch("tag_remove", {"key": "dead"})  # no force needed
        with pytest.raises(TagInUseError):
            dispatcher.dispatch("tag_remove", {"key": "auth"})

    def test_archived_documents_still_count(self, dispatcher: Dispatcher) -> None:
        # `tag rm` blocks on an archived document too, so a count that ignored
        # them would call a tag dead that then refuses to be removed.
        dispatcher.dispatch("tag_add", {"key": "auth", "description": "d"})
        doc = dispatcher.dispatch(
            "add", {"type": "decision", "title": "T", "description": "d", "tags": ["auth"]}
        )
        dispatcher.dispatch("archive", {"doc_id": doc["id"]})
        assert dispatcher.dispatch("tag_list", {})[0]["usage"] == 1
        with pytest.raises(TagInUseError):
            dispatcher.dispatch("tag_remove", {"key": "auth"})

    def test_the_count_follows_the_page(self, dispatcher: Dispatcher) -> None:
        _two_tags_and_three_docs(dispatcher)
        page = dispatcher.dispatch("tag_list", {"limit": 1, "offset": 1})
        assert [(t["key"], t["usage"]) for t in page] == [("authn", 1)]


def test_add_duplicate_rejected(dispatcher: Dispatcher) -> None:
    dispatcher.dispatch("tag_add", {"key": "auth", "description": "Auth."})
    with pytest.raises(TagAlreadyExistsError):
        dispatcher.dispatch("tag_add", {"key": "auth", "description": "again"})


def test_rename_rewrites_documents(seeded: Dispatcher) -> None:
    seeded.dispatch("tag_rename", {"old": "auth", "new": "authn"})
    doc = seeded.dispatch("get", {"doc_id": "adr-0001"})
    assert "authn" in doc["tags"] and "auth" not in doc["tags"]
    keys = {t["key"] for t in seeded.dispatch("tag_list", {})}
    assert "authn" in keys and "auth" not in keys


def test_rename_missing_rejected(dispatcher: Dispatcher) -> None:
    with pytest.raises(TagNotFoundError):
        dispatcher.dispatch("tag_rename", {"old": "ghost", "new": "x"})


def test_rename_to_existing_rejected(seeded: Dispatcher) -> None:
    with pytest.raises(TagAlreadyExistsError):
        seeded.dispatch("tag_rename", {"old": "auth", "new": "api"})


def test_remove_in_use_blocked(seeded: Dispatcher) -> None:
    with pytest.raises(TagInUseError):
        seeded.dispatch("tag_remove", {"key": "auth"})


def test_remove_force_strips_from_documents(seeded: Dispatcher) -> None:
    seeded.dispatch("tag_remove", {"key": "auth", "force": True})
    doc = seeded.dispatch("get", {"doc_id": "adr-0001"})
    assert "auth" not in doc["tags"]
    assert all(t["key"] != "auth" for t in seeded.dispatch("tag_list", {}))


def test_remove_missing_rejected(dispatcher: Dispatcher) -> None:
    with pytest.raises(TagNotFoundError):
        dispatcher.dispatch("tag_remove", {"key": "ghost"})


def test_remove_unused_tag(dispatcher: Dispatcher) -> None:
    dispatcher.dispatch("tag_add", {"key": "lonely", "description": "x"})
    dispatcher.dispatch("tag_remove", {"key": "lonely"})
    assert dispatcher.dispatch("tag_list", {}) == []


# -- the staleness clock (GAP-020) ------------------------------------------
#
# `stale_reference_date()` falls back to `updated` when a document has no
# explicit `verified`, and tag rename/rm rewrote every referencing document with
# `updated = today`. A pure classification edit therefore made overdue documents
# report as freshly reviewed — a bulk administrative action silently forging the
# one trust signal the product offers, which is what ADR-0006 argues staleness
# must never be. `check --fix` and `delete --force` already leave `updated`
# alone for the same reason.


def _overdue_decision(settings: Settings, tag: str) -> None:
    """A decision far past its 365-day cadence, carrying ``tag``."""
    decisions = settings.docs_root / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    (decisions / "adr-0001-old.md").write_text(
        "---\n"
        "created: '2024-01-01'\n"
        "description: an old decision\n"
        "id: adr-0001\n"
        "related: []\n"
        "status: accepted\n"
        f"tags: [{tag}]\n"
        "title: Old decision\n"
        "type: decision\n"
        "updated: '2024-01-01'\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )


def test_rename_does_not_reset_the_staleness_clock(
    dispatcher: Dispatcher, settings: Settings
) -> None:
    dispatcher.dispatch("tag_add", {"key": "auth", "description": "Auth."})
    _overdue_decision(settings, "auth")
    dispatcher.dispatch("reindex", {})
    assert dispatcher.dispatch("get", {"doc_id": "adr-0001"})["stale"] is True

    dispatcher.dispatch("tag_rename", {"old": "auth", "new": "authn"})

    view = dispatcher.dispatch("get", {"doc_id": "adr-0001"})
    assert list(view["tags"]) == ["authn"]  # the rename did happen
    assert view["updated"] == "2024-01-01"  # ...without touching the clock
    assert view["stale"] is True


def test_force_remove_does_not_reset_the_staleness_clock(
    dispatcher: Dispatcher, settings: Settings
) -> None:
    dispatcher.dispatch("tag_add", {"key": "auth", "description": "Auth."})
    _overdue_decision(settings, "auth")
    dispatcher.dispatch("reindex", {})

    dispatcher.dispatch("tag_remove", {"key": "auth", "force": True})

    view = dispatcher.dispatch("get", {"doc_id": "adr-0001"})
    assert list(view["tags"]) == []
    assert view["updated"] == "2024-01-01"
    assert view["stale"] is True


# -- consolidating two tags (GAP-028) ---------------------------------------
#
# Renaming onto an existing key was rejected outright, so two tags could never
# be merged: the only path was `tag rm --force` on one — throwing the
# classification away — and re-tagging by hand. Vocabularies drift and need
# consolidating; the registry could only grow.


def _two_tags_and_three_docs(dispatcher: Dispatcher) -> None:
    dispatcher.dispatch("tag_add", {"key": "auth", "description": "Old wording."})
    dispatcher.dispatch("tag_add", {"key": "authn", "description": "The wording we keep."})
    dispatcher.dispatch(
        "add", {"type": "decision", "title": "Only old", "description": "d", "tags": ["auth"]}
    )
    dispatcher.dispatch(
        "add",
        {"type": "decision", "title": "Both", "description": "d", "tags": ["auth", "authn"]},
    )
    dispatcher.dispatch("add", {"type": "decision", "title": "Neither", "description": "d"})


def test_rename_onto_existing_still_refused_without_merge(dispatcher: Dispatcher) -> None:
    # A merge discards one description, which is not what fixing a typo means.
    _two_tags_and_three_docs(dispatcher)
    with pytest.raises(TagAlreadyExistsError, match="--merge"):
        dispatcher.dispatch("tag_rename", {"old": "auth", "new": "authn"})


def test_merge_folds_the_tag_and_reports_the_documents(dispatcher: Dispatcher) -> None:
    _two_tags_and_three_docs(dispatcher)
    result = dispatcher.dispatch("tag_rename", {"old": "auth", "new": "authn", "merge": True})
    assert result["documents"] == ["adr-0001", "adr-0002"]
    keys = {t["key"] for t in dispatcher.dispatch("tag_list", {})}
    assert keys == {"authn"}


def test_a_document_carrying_both_tags_ends_with_one(dispatcher: Dispatcher) -> None:
    # The naive rewrite maps old->new in place and leaves ('authn', 'authn').
    _two_tags_and_three_docs(dispatcher)
    dispatcher.dispatch("tag_rename", {"old": "auth", "new": "authn", "merge": True})
    assert list(dispatcher.dispatch("get", {"doc_id": "adr-0002"})["tags"]) == ["authn"]


def test_the_surviving_tags_description_is_kept(dispatcher: Dispatcher) -> None:
    # `new` is the one being kept, so its wording is the one people chose.
    _two_tags_and_three_docs(dispatcher)
    dispatcher.dispatch("tag_rename", {"old": "auth", "new": "authn", "merge": True})
    tags = {t["key"]: t["description"] for t in dispatcher.dispatch("tag_list", {})}
    assert tags["authn"] == "The wording we keep."


def test_merge_does_not_reset_the_staleness_clock(
    dispatcher: Dispatcher, settings: Settings
) -> None:
    # Same rule as rename/rm: a bulk classification edit is not a re-verification.
    dispatcher.dispatch("tag_add", {"key": "auth", "description": "Old."})
    dispatcher.dispatch("tag_add", {"key": "authn", "description": "New."})
    _overdue_decision(settings, "auth")
    dispatcher.dispatch("reindex", {})

    dispatcher.dispatch("tag_rename", {"old": "auth", "new": "authn", "merge": True})

    view = dispatcher.dispatch("get", {"doc_id": "adr-0001"})
    assert list(view["tags"]) == ["authn"]
    assert view["updated"] == "2024-01-01"
    assert view["stale"] is True


def test_merge_still_requires_the_source_tag_to_exist(dispatcher: Dispatcher) -> None:
    dispatcher.dispatch("tag_add", {"key": "authn", "description": "New."})
    with pytest.raises(TagNotFoundError):
        dispatcher.dispatch("tag_rename", {"old": "ghost", "new": "authn", "merge": True})


def test_merge_onto_a_new_key_behaves_like_a_plain_rename(dispatcher: Dispatcher) -> None:
    # --merge on a target that does not exist must not become a second code path.
    dispatcher.dispatch("tag_add", {"key": "auth", "description": "Old."})
    dispatcher.dispatch(
        "add", {"type": "decision", "title": "T", "description": "d", "tags": ["auth"]}
    )
    dispatcher.dispatch("tag_rename", {"old": "auth", "new": "authn", "merge": True})
    assert {t["key"] for t in dispatcher.dispatch("tag_list", {})} == {"authn"}
    assert list(dispatcher.dispatch("get", {"doc_id": "adr-0001"})["tags"]) == ["authn"]


def test_force_remove_reports_the_documents_it_stripped(seeded: Dispatcher) -> None:
    """Guards GAP-030. A forced removal rewrites other people's files and said
    only `removed <key>` — the same silence `delete --force` and
    `tag rename --merge` were fixed for."""
    result = seeded.dispatch("tag_remove", {"key": "auth", "force": True})
    assert result["removed"] == "auth"
    assert result["documents"] == ["adr-0001", "issue-0001"]


def test_removing_an_unused_tag_reports_no_documents(dispatcher: Dispatcher) -> None:
    dispatcher.dispatch("tag_add", {"key": "spare", "description": "d"})
    assert dispatcher.dispatch("tag_remove", {"key": "spare"})["documents"] == []


def test_self_merge_is_rejected(dispatcher: Dispatcher) -> None:
    """A self-merge used to corrupt the registry (found by the 0.7.0 delta pass).

    `tag rename auth auth --merge` reported success, deleted `auth` from the
    registry, and left every document still carrying it — manufacturing exactly
    the `unknown-tag` state `check` reports. `delete(old)` runs unconditionally,
    and rewriting `old -> new` is a no-op when they are the same string, so
    nothing put the entry back.
    """
    dispatcher.dispatch("tag_add", {"key": "auth", "description": "Auth."})
    dispatcher.dispatch(
        "add", {"type": "decision", "title": "T", "description": "d", "tags": ["auth"]}
    )
    with pytest.raises(ValidationError):
        dispatcher.dispatch("tag_rename", {"old": "auth", "new": "auth", "merge": True})

    assert [t["key"] for t in dispatcher.dispatch("tag_list", {})] == ["auth"]
    assert list(dispatcher.dispatch("get", {"doc_id": "adr-0001"})["tags"]) == ["auth"]
    assert not [i for i in dispatcher.dispatch("check", {}) if i["kind"] == "unknown-tag"]


def test_self_rename_without_merge_is_rejected_too(dispatcher: Dispatcher) -> None:
    dispatcher.dispatch("tag_add", {"key": "auth", "description": "Auth."})
    with pytest.raises(ValidationError):
        dispatcher.dispatch("tag_rename", {"old": "auth", "new": "auth"})
