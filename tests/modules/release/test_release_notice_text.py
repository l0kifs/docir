"""What the ambient notice says, and the four installations it says it to.

`notice_for` is the decision table the one-line notice used to be: before it,
every installation was told to run `docir self upgrade`, and the package step of
that command declines for two of the six kinds — including `project`, which is
what docir's own checkout and every lockfile-managed project detect as.

`announce` is the throttle around it. Both are tested here rather than through
the CLI because the interesting cases are combinations of installation, cache
and day, and building them at the process boundary costs a subprocess each.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from docir.modules.release.api import notice_for
from docir.modules.release.application.ports import ProcessRunner, ReleaseCache, ReleaseIndex
from docir.modules.release.application.service import ReleaseService
from docir.modules.release.domain.installation import Installation
from docir.modules.release.domain.results import ReleaseStatus
from docir.platform.clock import Clock

TODAY = date(2026, 7, 7)


class FakeIndex(ReleaseIndex):
    """Counts, so "this never reached the network" is an assertion."""

    def __init__(self, version: str | None) -> None:
        self.version = version
        self.calls = 0

    def latest_version(self, package: str) -> str | None:
        self.calls += 1
        return self.version


class FakeCache(ReleaseCache):
    def __init__(self, entry: tuple[str, str] | None = None) -> None:
        self.entry = entry
        self.announcement: tuple[str, str] | None = None

    def read(self) -> tuple[str, str] | None:
        return self.entry

    def write(self, version: str, checked_on: str) -> None:
        self.entry = (version, checked_on)

    def read_announcement(self) -> tuple[str, str] | None:
        return self.announcement

    def record_announcement(self, version: str, on: str) -> None:
        self.announcement = (version, on)


class NeverRuns(ProcessRunner):
    def run(self, command: Sequence[str]) -> tuple[int, str]:
        raise AssertionError("announcing must never run an installer")


UV_TOOL = Installation("uv-tool", ("uv", "tool", "upgrade", "docir"), "owns its environment")
CHECKOUT = Installation("project", (), "belongs to a project; upgrade it there")
EPHEMERAL = Installation("uvx", (), "nothing here to upgrade; use `uvx docir@latest ...`")
UNKNOWN = Installation("unknown", (), "cannot tell how docir was installed")


class _FixedClock(Clock):
    def __init__(self, day: date) -> None:
        self._day = day

    def today(self) -> date:
        return self._day


def _status(installation: Installation, *, latest: str | None, installed: str = "0.11.0"):
    return ReleaseStatus(
        installed=installed,
        latest=latest,
        checked_on="2026-07-07",
        method=installation.method,
        upgrade_command=installation.upgrade_command,
        explanation=installation.explanation,
    )


class TestWhoIsTold:
    def test_an_owned_environment_is_told_the_command_and_the_moment(self) -> None:
        line = notice_for(_status(UV_TOOL, latest="0.12.0"))
        assert line is not None
        assert "docir 0.12.0 is available (this is 0.11.0)" in line
        # The moment, not just the command: `self upgrade` replaces this
        # process, respawns the daemon and rebuilds the index, and an agent
        # reading an instruction has no other way to know when that is safe.
        assert "docir self upgrade" in line
        assert "between tasks" in line

    def test_a_checkout_is_told_nothing_at_all(self) -> None:
        assert notice_for(_status(CHECKOUT, latest="0.12.0")) is None

    def test_an_ephemeral_run_is_told_how_to_pin(self) -> None:
        line = notice_for(_status(EPHEMERAL, latest="0.12.0"))
        assert line is not None
        assert "uvx docir@latest" in line
        assert "self upgrade" not in line

    def test_an_unrecognised_install_carries_its_own_reason(self) -> None:
        line = notice_for(_status(UNKNOWN, latest="0.12.0"))
        assert line is not None
        assert "cannot tell how docir was installed" in line
        assert "self upgrade" not in line


class TestWhenNothingIsSaid:
    def test_an_unknown_latest_is_not_a_notice(self) -> None:
        # Absent means nobody has checked, never "up to date".
        assert notice_for(_status(UV_TOOL, latest=None)) is None

    def test_the_same_version_is_not_a_notice(self) -> None:
        assert notice_for(_status(UV_TOOL, latest="0.11.0")) is None

    def test_an_older_published_version_is_not_a_notice(self) -> None:
        assert notice_for(_status(UV_TOOL, latest="0.10.0")) is None


class TestAnnouncingIsThrottled:
    def _service(self, cache: FakeCache, *, installation: Installation = UV_TOOL) -> ReleaseService:
        return ReleaseService(
            installation=installation,
            runner=NeverRuns(),
            index=FakeIndex("0.12.0"),
            cache=cache,
            clock=_FixedClock(TODAY),
            version="0.11.0",
        )

    def test_the_first_call_announces_and_records(self) -> None:
        cache = FakeCache(("0.12.0", TODAY.isoformat()))
        assert self._service(cache).announce() is not None
        assert cache.announcement == ("0.12.0", TODAY.isoformat())

    def test_the_second_call_the_same_day_is_silent(self) -> None:
        cache = FakeCache(("0.12.0", TODAY.isoformat()))
        service = self._service(cache)
        assert service.announce() is not None
        assert service.announce() is None

    def test_a_newer_release_the_same_day_announces_again(self) -> None:
        cache = FakeCache(("0.12.0", TODAY.isoformat()))
        assert self._service(cache).announce() is not None
        cache.entry = ("0.13.0", TODAY.isoformat())
        assert self._service(cache).announce() is not None

    def test_yesterdays_announcement_does_not_silence_today(self) -> None:
        cache = FakeCache(("0.12.0", TODAY.isoformat()))
        cache.announcement = ("0.12.0", "2026-07-06")
        assert self._service(cache).announce() is not None

    def test_a_silenced_installation_records_nothing(self) -> None:
        # Nothing was said, so nothing may be remembered as said: recording here
        # would make a store that *becomes* upgradable stay quiet for the day.
        cache = FakeCache(("0.12.0", TODAY.isoformat()))
        assert self._service(cache, installation=CHECKOUT).announce() is None
        assert cache.announcement is None

    def test_announcing_never_reaches_the_index(self) -> None:
        # The fetch is the daemon's job. A notice on a command someone is
        # waiting for must cost one file read and nothing else.
        cache = FakeCache(("0.12.0", TODAY.isoformat()))
        index = FakeIndex("0.13.0")
        ReleaseService(
            installation=UV_TOOL,
            runner=NeverRuns(),
            index=index,
            cache=cache,
            clock=_FixedClock(TODAY),
            version="0.11.0",
        ).announce()
        assert index.calls == 0
