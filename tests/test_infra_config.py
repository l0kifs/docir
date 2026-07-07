"""Tests for settings/path resolution."""

from __future__ import annotations

from pathlib import Path

from docir.infrastructure.config.settings import Settings


def test_resolve_uses_env(monkeypatch, tmp_path) -> None:
    home = tmp_path / "custom"
    monkeypatch.setenv("DOCIR_HOME", str(home))
    monkeypatch.delenv("DOCIR_NO_DAEMON", raising=False)
    settings = Settings.resolve()
    assert settings.home == home.resolve()
    assert settings.use_daemon is True


def test_no_daemon_env_disables_daemon(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DOCIR_HOME", str(tmp_path))
    monkeypatch.setenv("DOCIR_NO_DAEMON", "1")
    assert Settings.resolve().use_daemon is False


def test_explicit_home_and_paths(tmp_path) -> None:
    settings = Settings.resolve(tmp_path / "h", use_daemon=False)
    assert settings.docs_root == (tmp_path / "h" / "docs").resolve()
    assert settings.db_path.name == "index.db"
    assert settings.tags_path.name == "tags.yaml"
    assert settings.socket_path.name.startswith("docir-")
    assert settings.socket_path.suffix == ".sock"
    assert settings.pid_path.name == "daemon.pid"
    assert settings.log_path.name == "daemon.log"
    assert settings.database_url.startswith("sqlite:///")


def test_ensure_directories(tmp_path) -> None:
    settings = Settings.resolve(tmp_path / "h", use_daemon=False)
    settings.ensure_directories()
    assert Path(settings.docs_root).is_dir()
