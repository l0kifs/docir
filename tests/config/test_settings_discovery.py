"""Tests for project-local store discovery and home-resolution precedence."""

from __future__ import annotations

from pathlib import Path

from docir.config.settings import Settings, discover_project_home


class TestDiscoverProjectHome:
    def test_finds_store_from_a_subdirectory(self, tmp_path: Path) -> None:
        store = tmp_path / ".docir"
        store.mkdir()
        deep = tmp_path / "a" / "b"
        deep.mkdir(parents=True)
        assert discover_project_home(deep) == store.resolve()

    def test_nearest_store_wins(self, tmp_path: Path) -> None:
        (tmp_path / ".docir").mkdir()
        inner = tmp_path / "pkg"
        inner.mkdir()
        (inner / ".docir").mkdir()
        assert discover_project_home(inner / "sub") == (inner / ".docir").resolve()

    def test_returns_none_without_a_store(self, tmp_path: Path) -> None:
        # Assumes no `.docir` exists above the pytest tmp dir (true on CI/dev).
        assert discover_project_home(tmp_path) is None

    def test_ignores_a_docir_file(self, tmp_path: Path) -> None:
        (tmp_path / ".docir").write_text("not a dir", encoding="utf-8")
        assert discover_project_home(tmp_path) is None


class TestResolvePrecedence:
    def test_explicit_home_wins_over_everything(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("DOCIR_HOME", str(tmp_path / "env"))
        (tmp_path / ".docir").mkdir()
        monkeypatch.chdir(tmp_path)
        settings = Settings.resolve(home=tmp_path / "explicit")
        assert settings.home == (tmp_path / "explicit").resolve()

    def test_env_wins_over_discovery(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("DOCIR_HOME", str(tmp_path / "env"))
        (tmp_path / ".docir").mkdir()
        monkeypatch.chdir(tmp_path)
        assert Settings.resolve().home == (tmp_path / "env").resolve()

    def test_discovery_used_when_no_explicit_home_or_env(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("DOCIR_HOME", raising=False)
        store = tmp_path / ".docir"
        store.mkdir()
        sub = tmp_path / "sub"
        sub.mkdir()
        monkeypatch.chdir(sub)
        assert Settings.resolve().home == store.resolve()
