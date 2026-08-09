"""The release use cases: what is installed, what is published, upgrade it.

Two rules run through the whole thing.

**The network is opt-in and daily.** ``status`` reads the cache and stops there
unless it is asked to refresh, so the ambient notice on every command costs a
file read and docir stays a tool that works offline. A refresh is skipped when
the cache was already written today: the question is "is there a newer release",
and that answer does not change often enough to ask twice in a day.

**An installer runs only where docir owns its environment.** Everything else
returns the reason instead of a command — see :mod:`..domain.installation`.
"""

from __future__ import annotations

from docir.modules.release.application.ports import ProcessRunner, ReleaseCache, ReleaseIndex
from docir.modules.release.domain.installation import PACKAGE, Installation
from docir.modules.release.domain.results import ReleaseStatus, UpgradeOutcome
from docir.platform.clock import Clock


class ReleaseService:
    """Reports the installed/published gap and, where allowed, closes it."""

    def __init__(
        self,
        installation: Installation,
        runner: ProcessRunner,
        index: ReleaseIndex,
        cache: ReleaseCache,
        clock: Clock,
        version: str,
    ) -> None:
        self._installation = installation
        self._runner = runner
        self._index = index
        self._cache = cache
        self._clock = clock
        self._version = version

    def status(self, *, refresh: bool = False) -> ReleaseStatus:
        """The installed version against the newest known one.

        ``refresh`` asks the index; without it this is a file read. A refresh
        that fails leaves whatever was cached, because a stale answer is a
        better answer than none.
        """
        cached = self._cache.read()
        if refresh and not self._checked_today(cached):
            cached = self._fetch() or cached
        latest, checked_on = cached if cached is not None else (None, None)
        return ReleaseStatus(
            installed=self._version,
            latest=latest,
            checked_on=checked_on,
            method=self._installation.method,
            upgrade_command=self._installation.upgrade_command,
            explanation=self._installation.explanation,
        )

    def upgrade_package(self) -> UpgradeOutcome:
        """Run the installer, where there is one to run.

        Not the same as "there is a newer version": the installer is the thing
        that knows, and asking the index first would make an upgrade depend on a
        network call that the installer is about to make anyway.
        """
        command = self._installation.upgrade_command
        if not command:
            return UpgradeOutcome(
                ran=False, ok=True, command=(), message=self._installation.explanation
            )
        status, output = self._runner.run(command)
        return UpgradeOutcome(
            ran=True,
            ok=status == 0,
            command=command,
            message=output.strip() or f"`{' '.join(command)}` exited {status}",
        )

    # -- internals ----------------------------------------------------------

    def _checked_today(self, cached: tuple[str, str] | None) -> bool:
        return cached is not None and cached[1] == self._clock.today().isoformat()

    def _fetch(self) -> tuple[str, str] | None:
        latest = self._index.latest_version(PACKAGE)
        if latest is None:
            return None
        checked_on = self._clock.today().isoformat()
        self._cache.write(latest, checked_on)
        return latest, checked_on
