"""Concrete adapters: run a command, ask PyPI, remember the answer.

The PyPI client is stdlib ``urllib`` on a short timeout rather than a new HTTP
dependency. docir makes exactly one network call in its life — this one, opt-in
— and a courtesy check is not worth a dependency, a connection pool or a retry
policy. Every failure mode collapses to ``None``: unknown, not "up to date".
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path

from docir.modules.release.application.ports import (
    ProcessRunner,
    ReleaseCache,
    ReleaseIndex,
    VersionProbe,
)

#: Seconds to wait on PyPI. Short on purpose: this runs beside a command the
#: user is waiting for, and a slow answer to "is there a newer version" is worth
#: less than the second it costs.
_TIMEOUT = 3.0

#: Installers download, resolve and build; a minute is generous but finite, and
#: an installer wedged forever behind a prompt would hang the CLI.
_INSTALL_TIMEOUT = 300.0

#: Starting an interpreter and reading one dist-info. Short: this runs after an
#: installer has already finished, on a command somebody is waiting for.
_PROBE_TIMEOUT = 30.0

#: Printed by the probe's subprocess. ``importlib.metadata`` rather than
#: importing docir: the package is what was installed, and importing it would
#: also pay for every module docir loads at import time.
_VERSION_SNIPPET = "import importlib.metadata as m; print(m.version('docir'))"


class SubprocessRunner(ProcessRunner):
    """Runs the installer as a child process, capturing what it said."""

    def run(self, command: Sequence[str]) -> tuple[int, str]:
        try:
            completed = subprocess.run(
                list(command),
                capture_output=True,
                text=True,
                timeout=_INSTALL_TIMEOUT,
                check=False,
            )
        except FileNotFoundError:
            return 127, f"{command[0]}: not found on PATH"
        except subprocess.TimeoutExpired:
            return 124, f"`{' '.join(command)}` timed out"
        return completed.returncode, f"{completed.stdout}{completed.stderr}"


class PyPIReleaseIndex(ReleaseIndex):
    """The newest version from the PyPI JSON API."""

    def __init__(self, base_url: str = "https://pypi.org/pypi") -> None:
        self._base_url = base_url.rstrip("/")

    def latest_version(self, package: str) -> str | None:
        request = urllib.request.Request(
            f"{self._base_url}/{package}/json",
            headers={"Accept": "application/json", "User-Agent": "docir"},
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return None
        info = payload.get("info") if isinstance(payload, dict) else None
        version = info.get("version") if isinstance(info, dict) else None
        return str(version) if version else None


class JsonFileReleaseCache(ReleaseCache):
    """The last answer and the last announcement, as one JSON file in the store.

    Two facts in one file, written by two different processes — the daemon
    records what PyPI said, the CLI records that it told somebody — so every
    write is read-modify-write. Writing the whole document from either side
    would have each one silently erase the other's key, which fails in the
    direction that is hardest to notice: the notice would simply print on every
    command again, exactly as it does with no throttle at all.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> tuple[str, str] | None:
        return self._pair("latest", "checked_on")

    def write(self, version: str, checked_on: str) -> None:
        self._merge({"latest": version, "checked_on": checked_on})

    def read_announcement(self) -> tuple[str, str] | None:
        return self._pair("announced", "announced_on")

    def record_announcement(self, version: str, on: str) -> None:
        self._merge({"announced": version, "announced_on": on})

    # -- internals ----------------------------------------------------------

    def _document(self) -> dict[str, object]:
        """Whatever the file holds, or an empty document.

        Unreadable, absent and malformed are one case on purpose. This file is a
        cache of a courtesy check; the only thing a parse error may cost is one
        extra fetch, and raising here would turn a corrupt byte into a failure of
        whatever command the user actually ran.
        """
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _pair(self, version_key: str, date_key: str) -> tuple[str, str] | None:
        data = self._document()
        version, on = data.get(version_key), data.get(date_key)
        if not isinstance(version, str) or not isinstance(on, str):
            return None
        return version, on

    def _merge(self, fields: dict[str, str]) -> None:
        document = self._document()
        document.update(fields)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(document), encoding="utf-8")


class SubprocessVersionProbe(VersionProbe):
    """Asks a fresh interpreter what the environment now holds.

    A subprocess and not an import: ``importlib.metadata`` caches what it read
    when this process started, so asking in-process returns the version the
    installer replaced rather than the one it installed. A new interpreter reads
    the dist-info on disk, which is the fact.

    Every failure is ``None``. This runs to decide how to *word a report*, and a
    probe that raised would turn an upgrade that worked into a command that
    crashed after it.
    """

    def __init__(self, executable: str | None = None) -> None:
        self._executable = executable or sys.executable

    def installed_version(self) -> str | None:
        try:
            completed = subprocess.run(
                [self._executable, "-c", _VERSION_SNIPPET],
                capture_output=True,
                text=True,
                timeout=_PROBE_TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        version = completed.stdout.strip()
        return version if completed.returncode == 0 and version else None
