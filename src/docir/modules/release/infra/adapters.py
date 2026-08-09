"""Concrete adapters: run a command, ask PyPI, remember the answer.

The PyPI client is stdlib ``urllib`` on a short timeout rather than a new HTTP
dependency. docir makes exactly one network call in its life — this one, opt-in
— and a courtesy check is not worth a dependency, a connection pool or a retry
policy. Every failure mode collapses to ``None``: unknown, not "up to date".
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path

from docir.modules.release.application.ports import ProcessRunner, ReleaseCache, ReleaseIndex

#: Seconds to wait on PyPI. Short on purpose: this runs beside a command the
#: user is waiting for, and a slow answer to "is there a newer version" is worth
#: less than the second it costs.
_TIMEOUT = 3.0

#: Installers download, resolve and build; a minute is generous but finite, and
#: an installer wedged forever behind a prompt would hang the CLI.
_INSTALL_TIMEOUT = 300.0


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
    """The last answer, as one small JSON file in the store."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> tuple[str, str] | None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        version, checked_on = data.get("latest"), data.get("checked_on")
        if not isinstance(version, str) or not isinstance(checked_on, str):
            return None
        return version, checked_on

    def write(self, version: str, checked_on: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"latest": version, "checked_on": checked_on}), encoding="utf-8"
        )
