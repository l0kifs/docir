"""The ambient release notice: who is told, how often, and who is never told.

Four properties, all of them about restraint. The CLI never reaches the network
(it prints whatever the daemon cached, or nothing); it says a thing once a day
rather than on every command; it says nothing at all where the upgrade it would
name cannot be performed; and whether it speaks at all is a decision somebody
recorded — in this shell, in CI, or in the store.

The installation is injected here rather than detected. Every test in this suite
runs from an editable checkout, which classifies as ``project`` — the one kind
that is deliberately never told to upgrade — so a test that let detection run
would assert silence for the wrong reason and keep passing after the notice
broke.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from typer.testing import CliRunner

from docir.config.settings import Settings
from docir.entry_points.cli.app import app
from docir.entry_points.daemon.release_watch import ReleaseWatcher
from docir.modules.release.api import Installation, ReleaseService
from docir.modules.release.application.ports import ProcessRunner, ReleaseCache, ReleaseIndex
from docir.modules.release.domain.installation import Evidence
from docir.platform.clock import SystemClock

runner = CliRunner()

#: An environment docir owns, so `docir self upgrade` is a real instruction.
OWNED = Evidence(
    prefix=Path("/nonexistent/env"),
    executable=Path("/nonexistent/env/bin/python"),
    has_uv_receipt=True,
    has_pipx_metadata=False,
    direct_url=None,
    editable=False,
    ephemeral=False,
)


def _installed_as(monkeypatch, evidence: Evidence) -> None:
    """Make detection see ``evidence`` instead of this checkout."""
    monkeypatch.setattr("docir.modules.release.api.gather_evidence", lambda: evidence)


def _cache_says(settings: Settings, version: str) -> None:
    settings.ensure_directories()
    settings.release_cache_path.write_text(
        json.dumps({"latest": version, "checked_on": "2026-07-07"}), encoding="utf-8"
    )


def _query(monkeypatch, *, opted_in: bool | None = True, ci: bool = False):
    """Run one command with both inputs to the decision pinned.

    ``CI`` is set explicitly on every call, never inherited. GitHub Actions
    exports ``CI=true``, so a test that reads the ambient value asserts one thing
    on a laptop and another on a build server — which is exactly what happened to
    the commit that added this file: green here, red there, on the one test whose
    opt-in came from the store rather than the environment.
    """
    if opted_in is not None:
        monkeypatch.setenv("DOCIR_UPDATE_CHECK", "1" if opted_in else "0")
    else:
        monkeypatch.delenv("DOCIR_UPDATE_CHECK", raising=False)
    if ci:
        monkeypatch.setenv("CI", "true")
    else:
        monkeypatch.delenv("CI", raising=False)
    result = runner.invoke(app, ["--no-daemon", "query", "--limit", "1"])
    assert result.exit_code == 0, result.output
    return result


class TestItSpeaksOnlyWhenAsked:
    def test_it_says_nothing_by_default(self, monkeypatch, settings: Settings) -> None:
        # Off unless somebody opted in: this is docir's only network call, and a
        # documentation tool that phones home unasked is not one people keep
        # (adr-a555ee6bc484).
        _installed_as(monkeypatch, OWNED)
        _cache_says(settings, "99.0.0")
        assert "available" not in _query(monkeypatch, opted_in=False).stderr

    def test_it_names_the_newer_release_when_asked_to(
        self, monkeypatch, settings: Settings
    ) -> None:
        _installed_as(monkeypatch, OWNED)
        _cache_says(settings, "99.0.0")
        stderr = _query(monkeypatch).stderr
        assert "docir 99.0.0 is available" in stderr
        assert "docir self upgrade" in stderr

    def test_an_older_cached_answer_is_not_a_notice(self, monkeypatch, settings: Settings) -> None:
        _installed_as(monkeypatch, OWNED)
        _cache_says(settings, "0.0.1")
        assert "available" not in _query(monkeypatch).stderr

    def test_no_cached_answer_is_silence_rather_than_a_network_call(
        self, monkeypatch, settings: Settings
    ) -> None:
        # Unknown says nothing. If this ever reached PyPI, the whole suite would
        # depend on being online — and the reply would outlive the process that
        # asked for it, which is why the fetch is the daemon's job.
        _installed_as(monkeypatch, OWNED)
        assert "available" not in _query(monkeypatch).stderr


class TestItSaysItOnceADay:
    def test_a_second_command_the_same_day_is_silent(self, monkeypatch, settings: Settings) -> None:
        _installed_as(monkeypatch, OWNED)
        _cache_says(settings, "99.0.0")
        assert "docir 99.0.0 is available" in _query(monkeypatch).stderr
        assert "available" not in _query(monkeypatch).stderr

    def test_a_newer_release_is_announced_again(self, monkeypatch, settings: Settings) -> None:
        # The throttle is keyed on the version as well as the day, so a release
        # published the same afternoon is not swallowed by the morning's notice.
        _installed_as(monkeypatch, OWNED)
        _cache_says(settings, "99.0.0")
        assert "docir 99.0.0 is available" in _query(monkeypatch).stderr
        _cache_says(settings, "99.1.0")
        assert "docir 99.1.0 is available" in _query(monkeypatch).stderr

    def test_the_throttle_does_not_erase_the_fetched_answer(
        self, monkeypatch, settings: Settings
    ) -> None:
        # One file, two writers. Recording the announcement re-writes the file
        # the daemon fetched into, and dropping `latest` there would send the
        # daemon back to PyPI and re-announce on the next command.
        _installed_as(monkeypatch, OWNED)
        _cache_says(settings, "99.0.0")
        _query(monkeypatch)
        document = json.loads(settings.release_cache_path.read_text(encoding="utf-8"))
        assert document["latest"] == "99.0.0"
        assert document["checked_on"] == "2026-07-07"
        assert document["announced"] == "99.0.0"


class TestAnInstallationThatCannotUpgradeIsNotToldTo:
    def test_a_checkout_is_never_told_to_upgrade(self, monkeypatch, settings: Settings) -> None:
        # docir's own repository, on the day it publishes the release. The
        # package step of `self upgrade` declines for a `project` install, so
        # the instruction would be unfollowable and would repeat forever.
        _installed_as(
            monkeypatch,
            Evidence(
                prefix=Path("/nonexistent/env"),
                executable=Path("/nonexistent/env/bin/python"),
                has_uv_receipt=False,
                has_pipx_metadata=False,
                direct_url="file:///repo",
                editable=True,
                ephemeral=False,
            ),
        )
        _cache_says(settings, "99.0.0")
        assert "available" not in _query(monkeypatch).stderr

    def test_an_ephemeral_uvx_run_is_told_how_to_pin_instead(
        self, monkeypatch, settings: Settings
    ) -> None:
        # There is nothing to upgrade, but there *is* an answer, so this one is
        # told — with the command that works rather than the one that does not.
        _installed_as(
            monkeypatch,
            Evidence(
                prefix=Path("/nonexistent/env"),
                executable=Path("/nonexistent/env/bin/python"),
                has_uv_receipt=False,
                has_pipx_metadata=False,
                direct_url=None,
                editable=False,
                ephemeral=True,
            ),
        )
        _cache_says(settings, "99.0.0")
        stderr = _query(monkeypatch).stderr
        assert "docir 99.0.0 is available" in stderr
        assert "uvx docir@latest" in stderr
        assert "self upgrade" not in stderr


class TestWhoDecidesWhetherItRuns:
    def test_the_store_config_opts_in(self, monkeypatch, settings: Settings) -> None:
        _installed_as(monkeypatch, OWNED)
        _cache_says(settings, "99.0.0")
        settings.store_config_path.write_text("update_check: true\n", encoding="utf-8")
        assert "docir 99.0.0 is available" in _query(monkeypatch, opted_in=None).stderr

    def test_the_environment_overrides_the_store(self, monkeypatch, settings: Settings) -> None:
        # Both directions matter; this is the one that lets a person on a team
        # opt out of a committed decision.
        _installed_as(monkeypatch, OWNED)
        _cache_says(settings, "99.0.0")
        settings.store_config_path.write_text("update_check: true\n", encoding="utf-8")
        assert "available" not in _query(monkeypatch, opted_in=False).stderr

    def test_ci_is_never_told(self, monkeypatch, settings: Settings) -> None:
        # A build server cannot act on it, and an agent that acts on it there
        # makes the job's docir version depend on the day it ran.
        _installed_as(monkeypatch, OWNED)
        _cache_says(settings, "99.0.0")
        settings.store_config_path.write_text("update_check: true\n", encoding="utf-8")
        assert "available" not in _query(monkeypatch, opted_in=None, ci=True).stderr

    def test_an_explicit_opt_in_beats_ci(self, monkeypatch, settings: Settings) -> None:
        _installed_as(monkeypatch, OWNED)
        _cache_says(settings, "99.0.0")
        assert "docir 99.0.0 is available" in _query(monkeypatch, ci=True).stderr

    def test_a_malformed_store_config_costs_the_notice_and_not_the_command(
        self, monkeypatch, settings: Settings
    ) -> None:
        # Read on every command, before anything the user asked for happens,
        # from a file a person may hand-edit.
        _installed_as(monkeypatch, OWNED)
        _cache_says(settings, "99.0.0")
        settings.store_config_path.write_text("update_check: [unclosed\n", encoding="utf-8")
        result = _query(monkeypatch, opted_in=None)
        assert result.exit_code == 0
        assert "available" not in result.stderr


class _CountingIndex(ReleaseIndex):
    def __init__(self) -> None:
        self.calls = 0

    def latest_version(self, package: str) -> str | None:
        self.calls += 1
        return "0.12.0"


class _MemoryCache(ReleaseCache):
    def __init__(self) -> None:
        self.entry: tuple[str, str] | None = None
        self.announcement: tuple[str, str] | None = None

    def read(self) -> tuple[str, str] | None:
        return self.entry

    def write(self, version: str, checked_on: str) -> None:
        self.entry = (version, checked_on)

    def read_announcement(self) -> tuple[str, str] | None:
        return self.announcement

    def record_announcement(self, version: str, on: str) -> None:
        self.announcement = (version, on)


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
