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

from docir.modules.release.application.ports import (
    ProcessRunner,
    ReleaseCache,
    ReleaseIndex,
    VersionProbe,
)
from docir.modules.release.domain.installation import PACKAGE, Installation
from docir.modules.release.domain.notice import notice_for
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
        probe: VersionProbe | None = None,
    ) -> None:
        self._installation = installation
        self._runner = runner
        self._index = index
        self._cache = cache
        self._clock = clock
        self._version = version
        # Optional so every existing caller and fake keeps working; the default
        # reports *unknown*, which is the answer that changes no behaviour.
        self._probe = probe or _UnknownVersion()

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

    def announce(self) -> str | None:
        """The line to print about a newer release, or ``None`` to stay quiet.

        Reads the cache and never the network — the fetch is the daemon's job —
        so this costs one file read on a command someone is waiting for.

        **It is a write as well as a read**, and that is the throttle: the store
        remembers which version it last announced and on which day, and says it
        again only when one of the two has moved. Without that, one release
        prints on every command until somebody upgrades, which is how the
        warning docir wants read becomes the warning a reader learns to skip —
        the same argument ``schema_notice`` settles one field over. `docir self
        status` is the unthrottled answer, for the reader who is asking.
        """
        status = self.status()
        text = notice_for(status)
        if text is None:
            return None
        today = self._clock.today().isoformat()
        if self._cache.read_announcement() == (status.latest, today):
            return None
        # ``latest`` is a string wherever ``notice_for`` returned a line: it is
        # what ``update_available`` compared.
        self._cache.record_announcement(str(status.latest), today)
        return text

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
        # Asked only after a *successful* run: a failed installer's version is
        # not a question anybody has, and the probe costs an interpreter start.
        after = self._probe.installed_version() if status == 0 else None
        return UpgradeOutcome(
            ran=True,
            ok=status == 0,
            command=command,
            message=output.strip() or f"`{' '.join(command)}` exited {status}",
            installed_before=self._version,
            installed_after=after,
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


class _UnknownVersion(VersionProbe):
    """The default probe: it cannot tell, and says so.

    Present so that adding the port did not change what any existing caller
    does. ``None`` flows into ``UpgradeOutcome.version_moved`` as *unknown*, and
    unknown is the value every caller already falls through on.
    """

    def installed_version(self) -> str | None:
        return None
