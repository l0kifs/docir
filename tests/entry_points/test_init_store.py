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


def test_force_overwrites_schema(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    initialize_store(settings)
    settings.schema_path.write_text("profiles: [research]\n", encoding="utf-8")
    result = initialize_store(settings, force=True)
    assert result.schema_written is True
    assert "profiles: [software]" in settings.schema_path.read_text(encoding="utf-8")
