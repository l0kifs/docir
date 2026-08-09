"""The opt-in release notice, and the daemon thread that keeps it true.

Two properties, both about restraint: the CLI never reaches the network (it
prints whatever the daemon cached, or nothing), and it says nothing at all
unless asked to.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from typer.testing import CliRunner

from docir.config.settings import Settings
from docir.entry_points.cli.app import app
from docir.entry_points.daemon.release_watch import ReleaseWatcher
from docir.modules.release.api import Installation, ReleaseService
from docir.modules.release.application.ports import ProcessRunner, ReleaseCache, ReleaseIndex
from docir.platform.clock import SystemClock

runner = CliRunner()


def _cache_says(settings: Settings, version: str) -> None:
    settings.ensure_directories()
    settings.release_cache_path.write_text(
        json.dumps({"latest": version, "checked_on": "2026-07-07"}), encoding="utf-8"
    )


def _query(monkeypatch, settings: Settings, *, opted_in: bool):
    monkeypatch.setenv("DOCIR_UPDATE_CHECK", "1" if opted_in else "0")
    result = runner.invoke(app, ["--no-daemon", "query", "--limit", "1"])
    assert result.exit_code == 0, result.output
    return result


def test_it_says_nothing_by_default(monkeypatch, settings: Settings) -> None:
    # Off by default for the reason `schema_notice` is: a warning on every
    # command until someone acts on it stops being read.
    _cache_says(settings, "99.0.0")
    assert "available" not in _query(monkeypatch, settings, opted_in=False).stderr


def test_it_names_the_newer_release_when_asked_to(monkeypatch, settings: Settings) -> None:
    _cache_says(settings, "99.0.0")
    assert "docir 99.0.0 is available" in _query(monkeypatch, settings, opted_in=True).stderr


def test_an_older_cached_answer_is_not_a_notice(monkeypatch, settings: Settings) -> None:
    _cache_says(settings, "0.0.1")
    assert "available" not in _query(monkeypatch, settings, opted_in=True).stderr


def test_no_cached_answer_is_silence_rather_than_a_network_call(
    monkeypatch, settings: Settings
) -> None:
    # Unknown says nothing. If this ever reached PyPI, the whole suite would
    # depend on being online.
    assert "available" not in _query(monkeypatch, settings, opted_in=True).stderr


class _CountingIndex(ReleaseIndex):
    def __init__(self) -> None:
        self.calls = 0

    def latest_version(self, package: str) -> str | None:
        self.calls += 1
        return "0.12.0"


class _MemoryCache(ReleaseCache):
    def __init__(self) -> None:
        self.entry: tuple[str, str] | None = None

    def read(self) -> tuple[str, str] | None:
        return self.entry

    def write(self, version: str, checked_on: str) -> None:
        self.entry = (version, checked_on)


class _NeverRuns(ProcessRunner):
    def run(self, command: Sequence[str]) -> tuple[int, str]:
        raise AssertionError("the watcher must never run an installer")


def test_the_daemon_watcher_fetches_once_on_start(settings: Settings) -> None:
    index, cache = _CountingIndex(), _MemoryCache()
    service = ReleaseService(
        installation=Installation("project", (), "belongs to a project"),
        runner=_NeverRuns(),
        index=index,
        cache=cache,
        clock=SystemClock(),
        version="0.11.0",
    )
    watcher = ReleaseWatcher(settings, service)
    watcher.start()
    watcher.stop()

    assert index.calls == 1
    assert cache.entry is not None and cache.entry[0] == "0.12.0"
    # The refresh swallows exceptions so a failed check cannot end the thread,
    # which means a broken service would leave these assertions passing on the
    # way past the failure. Ask the service directly for the answer it left.
    assert service.status().latest == "0.12.0"
