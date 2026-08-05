"""Tests for ``initialize_store`` — the ``docir init`` bootstrap in composition."""

from __future__ import annotations

from pathlib import Path

import pytest

from docir.config.settings import Settings
from docir.entry_points.composition import initialize_store
from docir.platform.errors import SchemaError


def _settings(tmp_path: Path) -> Settings:
    return Settings.resolve(home=tmp_path / ".docir", use_daemon=False)


def test_creates_schema_gitignore_and_index(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    result = initialize_store(settings)
    assert (settings.home / "docs-schema.yaml").exists()
    assert (settings.home / ".gitignore").exists()
    assert settings.db_path.exists()
    assert result.schema_written and result.gitignore_written
    assert result.profiles == ("software",)


def test_gitignore_excludes_the_derived_index(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    initialize_store(settings)
    text = (settings.home / ".gitignore").read_text(encoding="utf-8")
    assert "index.db" in text
    assert "daemon.pid" in text


def test_custom_profiles_are_written(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    result = initialize_store(settings, profiles=("research", "ops"))
    assert "profiles: [research, ops]" in settings.schema_path.read_text(encoding="utf-8")
    assert result.profiles == ("research", "ops")


def test_unknown_profile_raises(tmp_path: Path) -> None:
    with pytest.raises(SchemaError):
        initialize_store(_settings(tmp_path), profiles=("bogus",))


def test_idempotent_preserves_user_schema(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    initialize_store(settings)
    settings.schema_path.write_text("profiles: [research]\n", encoding="utf-8")
    result = initialize_store(settings)  # no force
    assert result.schema_written is False
    assert "research" in settings.schema_path.read_text(encoding="utf-8")


def test_force_rewrites_an_untouched_schema(tmp_path: Path) -> None:
    # Identical bytes: rewriting loses nothing, so --force alone is enough.
    settings = _settings(tmp_path)
    initialize_store(settings)
    result = initialize_store(settings, force=True)
    assert result.schema_written is True
    assert "profiles: [software]" in settings.schema_path.read_text(encoding="utf-8")


class TestForceProtectsACustomisedSchema:
    """`--force` no longer destroys a customised schema (guards issue-fde9a7151bd1).

    `--force` overwrote `docs-schema.yaml` and `.gitignore` under one flag, so
    re-running `init` to refresh the gitignore silently replaced every type,
    status and cadence a person had decided on — the one file in the store that
    cannot be rebuilt from the documents.

    The predecessor of this test was named `test_force_overwrites_schema` and
    asserted exactly that clobbering, so the suite could never have caught it.
    """

    @staticmethod
    def _customise(settings) -> str:
        settings.schema_path.write_text("profiles: [research]\n", encoding="utf-8")
        return "profiles: [research]"

    def test_force_alone_keeps_the_file_and_says_so(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        initialize_store(settings)
        custom = self._customise(settings)
        result = initialize_store(settings, force=True)
        assert custom in settings.schema_path.read_text(encoding="utf-8")
        assert result.schema_written is False
        assert result.schema_preserved is True

    def test_force_schema_replaces_it_when_asked(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        initialize_store(settings)
        self._customise(settings)
        result = initialize_store(settings, force=True, force_schema=True)
        assert result.schema_written is True
        assert "profiles: [software]" in settings.schema_path.read_text(encoding="utf-8")

    def test_the_gitignore_is_refreshed_even_when_the_schema_is_kept(self, tmp_path: Path) -> None:
        # The whole point, and why this skips rather than raises: refreshing the
        # gitignore is the thing the user came for, and an exception would abort
        # before it was written.
        settings = _settings(tmp_path)
        initialize_store(settings)
        self._customise(settings)
        gitignore = settings.home / ".gitignore"
        gitignore.write_text("stale contents\n", encoding="utf-8")

        result = initialize_store(settings, force=True)

        assert "index.db" in gitignore.read_text(encoding="utf-8")
        assert result.gitignore_written is True
        assert result.schema_preserved is True

    def test_an_unmodified_schema_is_not_reported_as_preserved(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        initialize_store(settings)
        result = initialize_store(settings, force=True)
        assert result.schema_preserved is False


class TestAShadowedStoreIsReported:
    """issue-e10cde8c5085: `init` beneath an existing store captured every command run
    under it, and said nothing.

    Discovery walks *up*, so the nested store wins for the whole subtree and the
    outer store's `check` never sees documents added there — they are not
    orphaned or dangling, they are in a different corpus. adr-20eec6e2e2ca is right that
    `init` must not *reuse* a parent store; that is a different decision from
    not mentioning it.
    """

    def test_a_store_above_is_reported(self, tmp_path: Path) -> None:
        initialize_store(_settings(tmp_path))
        nested = tmp_path / "team"
        nested.mkdir()
        result = initialize_store(_settings(nested))
        assert result.enclosing_home == (tmp_path / ".docir").resolve()

    def test_a_store_with_nothing_above_reports_none(self, tmp_path: Path) -> None:
        # Distinguishes "nothing is above" from "the check did not run".
        assert initialize_store(_settings(tmp_path)).enclosing_home is None

    def test_re_initialising_does_not_report_itself(self, tmp_path: Path) -> None:
        initialize_store(_settings(tmp_path))
        assert initialize_store(_settings(tmp_path), force=True).enclosing_home is None

    def test_a_deeply_nested_store_finds_the_nearest_one(self, tmp_path: Path) -> None:
        initialize_store(_settings(tmp_path))
        middle = tmp_path / "a"
        middle.mkdir()
        initialize_store(_settings(middle))
        deep = middle / "b" / "c"
        deep.mkdir(parents=True)
        assert initialize_store(_settings(deep)).enclosing_home == (middle / ".docir").resolve()

    def test_an_explicitly_named_store_still_notices_a_sibling(self, tmp_path: Path) -> None:
        # `--home /srv/docs` does not end in `.docir`, so the walk has to start
        # at the store's own directory rather than its parent.
        initialize_store(_settings(tmp_path))
        named = Settings.resolve(home=tmp_path / "docs", use_daemon=False)
        assert initialize_store(named).enclosing_home == (tmp_path / ".docir").resolve()
