"""Tests for project-local store discovery and home-resolution precedence."""

from __future__ import annotations

from pathlib import Path

import pytest

from docir.config.settings import (
    Settings,
    discover_project_home,
    new_store_home,
)


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


class TestGlobalFallbackIsDistinguishable:
    """A write must not land in the global store unannounced (guards issue-34b4f0ca1e13).

    `Settings.resolve` fell back to `~/.docir` with no signal, and the reported
    `path` is relative to the *store* — so in a repository nobody had run
    `docir init` in, the output read as repo-local while the file went to the
    user's home directory, ungitted and invisible to teammates. No error at any
    point.

    The global store is a real feature, so the fallback itself is not the
    defect; being unable to tell it apart from a deliberate choice is.
    """

    def test_origin_records_how_home_was_chosen(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("DOCIR_HOME", raising=False)
        monkeypatch.chdir(tmp_path)
        assert Settings.resolve(tmp_path / "x").home_origin == "flag"
        monkeypatch.setenv("DOCIR_HOME", str(tmp_path / "env"))
        assert Settings.resolve().home_origin == "env"
        monkeypatch.delenv("DOCIR_HOME")
        (tmp_path / ".docir").mkdir()
        assert Settings.resolve().home_origin == "project"

    def test_fallback_inside_a_repo_is_flagged(self, tmp_path: Path, monkeypatch) -> None:
        # The surprise case: a git repo nobody ran `docir init` in.
        (tmp_path / ".git").mkdir()
        monkeypatch.delenv("DOCIR_HOME", raising=False)
        monkeypatch.chdir(tmp_path)
        settings = Settings.resolve()
        assert settings.home_origin == "global"
        assert settings.is_unintended_global_fallback() is True

    def test_fallback_outside_a_repo_is_not_flagged(self, tmp_path: Path, monkeypatch) -> None:
        # No repo, no ambiguity — warning here would fire on correct usage.
        monkeypatch.delenv("DOCIR_HOME", raising=False)
        monkeypatch.chdir(tmp_path)
        assert Settings.resolve().is_unintended_global_fallback() is False

    def test_a_project_store_is_never_flagged(self, tmp_path: Path, monkeypatch) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".docir").mkdir()
        monkeypatch.delenv("DOCIR_HOME", raising=False)
        monkeypatch.chdir(tmp_path)
        assert Settings.resolve().is_unintended_global_fallback() is False

    def test_explicit_docir_home_opts_out(self, tmp_path: Path, monkeypatch) -> None:
        # Someone who *does* mean the global store from inside a repo says so
        # with DOCIR_HOME — no new flag needed, and it takes the `env` branch.
        (tmp_path / ".git").mkdir()
        monkeypatch.setenv("DOCIR_HOME", str(tmp_path / "chosen"))
        monkeypatch.chdir(tmp_path)
        assert Settings.resolve().is_unintended_global_fallback() is False


class TestNewStoreHome:
    """The `docir init` home rule lives beside `resolve` (guards issue-638068ed09a6).

    `init` computed its home in the CLI layer and never consulted `--home`, so
    the store landed in whatever directory the shell was in. The two home
    decisions in this codebase now sit in one module: a review that reads one
    reads the other.
    """

    def test_explicit_home_names_the_store_directly(self, tmp_path: Path) -> None:
        store = tmp_path / "srv" / "docs"
        assert new_store_home(None, store) == store.resolve()

    def test_directory_gets_a_dot_docir(self, tmp_path: Path) -> None:
        assert new_store_home(tmp_path / "proj", None) == (tmp_path / "proj").resolve() / ".docir"

    def test_neither_uses_the_cwd(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        assert new_store_home(None, None) == tmp_path.resolve() / ".docir"

    def test_both_conflict(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="pass one"):
            new_store_home(tmp_path / "proj", tmp_path / "store")

    def test_it_does_not_discover_a_parent_store(self, tmp_path: Path, monkeypatch) -> None:
        # `resolve` walks up for an existing `.docir`; creating one must not,
        # or `init` in a subdirectory would silently adopt the parent's store.
        (tmp_path / ".docir").mkdir()
        sub = tmp_path / "sub"
        sub.mkdir()
        monkeypatch.chdir(sub)
        assert new_store_home(None, None) == sub.resolve() / ".docir"
