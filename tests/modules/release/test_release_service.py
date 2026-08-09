"""The two decisions the release service makes: when to fetch, and when to install."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pytest

from docir.modules.release.application.ports import ProcessRunner, ReleaseCache, ReleaseIndex
from docir.modules.release.application.service import ReleaseService
from docir.modules.release.domain.installation import Installation
from docir.modules.release.domain.results import is_newer
from docir.platform.clock import Clock


class _FixedClock(Clock):
    """Frozen, because "did we already check today" is the decision under test."""

    def __init__(self, day: date) -> None:
        self._day = day

    def today(self) -> date:
        return self._day


class FakeIndex(ReleaseIndex):
    def __init__(self, version: str | None) -> None:
        self.version = version
        self.calls = 0

    def latest_version(self, package: str) -> str | None:
        self.calls += 1
        return self.version


class FakeCache(ReleaseCache):
    def __init__(self, entry: tuple[str, str] | None = None) -> None:
        self.entry = entry

    def read(self) -> tuple[str, str] | None:
        return self.entry

    def write(self, version: str, checked_on: str) -> None:
        self.entry = (version, checked_on)


class RecordingRunner(ProcessRunner):
    def __init__(self, status: int = 0, output: str = "upgraded") -> None:
        self.commands: list[tuple[str, ...]] = []
        self._status = status
        self._output = output

    def run(self, command: Sequence[str]) -> tuple[int, str]:
        self.commands.append(tuple(command))
        return self._status, self._output


UPGRADABLE = Installation("uv-tool", ("uv", "tool", "upgrade", "docir"), "owns its environment")
FROZEN = Installation("project", (), "belongs to a project")
TODAY = date(2026, 7, 7)


def _service(
    installation: Installation = UPGRADABLE,
    *,
    index: ReleaseIndex | None = None,
    cache: ReleaseCache | None = None,
    runner: ProcessRunner | None = None,
    version: str = "0.11.0",
) -> ReleaseService:
    return ReleaseService(
        installation=installation,
        runner=runner or RecordingRunner(),
        index=index or FakeIndex("0.12.0"),
        cache=cache or FakeCache(),
        clock=_FixedClock(TODAY),
        version=version,
    )


class TestTheNetworkIsOptInAndDaily:
    def test_status_without_refresh_never_asks(self) -> None:
        index = FakeIndex("0.12.0")
        status = _service(index=index).status()
        assert index.calls == 0
        assert status.latest is None, "unknown, not up to date"

    def test_refresh_asks_and_records_the_date(self) -> None:
        cache = FakeCache()
        status = _service(index=FakeIndex("0.12.0"), cache=cache).status(refresh=True)
        assert (status.latest, status.checked_on) == ("0.12.0", TODAY.isoformat())
        assert cache.entry == ("0.12.0", TODAY.isoformat())

    def test_a_second_refresh_the_same_day_does_not_ask_again(self) -> None:
        index = FakeIndex("0.12.0")
        cache = FakeCache(("0.12.0", TODAY.isoformat()))
        _service(index=index, cache=cache).status(refresh=True)
        assert index.calls == 0

    def test_a_refresh_the_next_day_asks_again(self) -> None:
        index = FakeIndex("0.13.0")
        cache = FakeCache(("0.12.0", "2026-07-06"))
        assert _service(index=index, cache=cache).status(refresh=True).latest == "0.13.0"
        assert index.calls == 1

    def test_an_unreachable_index_keeps_the_stale_answer(self) -> None:
        # A stale answer beats none: the machine being offline is not news
        # about docir, and the cached version is still the last thing known.
        cache = FakeCache(("0.12.0", "2026-01-01"))
        status = _service(index=FakeIndex(None), cache=cache).status(refresh=True)
        assert (status.latest, status.checked_on) == ("0.12.0", "2026-01-01")

    def test_an_unreachable_index_with_no_cache_stays_unknown(self) -> None:
        status = _service(index=FakeIndex(None), cache=FakeCache()).status(refresh=True)
        assert status.latest is None and status.update_available is False


class TestTheInstallerRunsOnlyWhereItMay:
    def test_it_runs_the_command_for_an_owned_environment(self) -> None:
        runner = RecordingRunner()
        outcome = _service(UPGRADABLE, runner=runner).upgrade_package()
        assert runner.commands == [("uv", "tool", "upgrade", "docir")]
        assert (outcome.ran, outcome.ok) == (True, True)

    def test_it_runs_nothing_where_docir_does_not_own_the_environment(self) -> None:
        runner = RecordingRunner()
        outcome = _service(FROZEN, runner=runner).upgrade_package()
        assert runner.commands == []
        assert (outcome.ran, outcome.ok) == (False, True)
        assert outcome.message == FROZEN.explanation

    def test_a_failing_installer_is_reported_rather_than_raised(self) -> None:
        runner = RecordingRunner(status=1, output="could not resolve docir")
        outcome = _service(UPGRADABLE, runner=runner).upgrade_package()
        assert (outcome.ran, outcome.ok) == (True, False)
        assert "could not resolve docir" in outcome.message

    def test_it_does_not_consult_the_index_first(self) -> None:
        # The installer is the thing that knows whether there is anything newer,
        # and it is about to ask anyway.
        index = FakeIndex("0.11.0")
        _service(UPGRADABLE, index=index).upgrade_package()
        assert index.calls == 0


@pytest.mark.parametrize(
    ("candidate", "installed", "expected"),
    [
        ("0.12.0", "0.11.0", True),
        ("0.10.0", "0.9.0", True),  # string/tuple compares get this one wrong
        ("0.11.0", "0.11.0", False),
        ("0.11.0", "0.12.0", False),
        ("1.0.0rc1", "0.12.0", True),
        ("1.0.0", "1.0.0rc1", True),
        ("not-a-version", "0.11.0", False),  # unorderable reads as "no idea"
        (None, "0.11.0", False),
    ],
)
def test_version_ordering(candidate: str | None, installed: str, expected: bool) -> None:
    assert is_newer(candidate, than=installed) is expected
