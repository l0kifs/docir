"""Keep the "is there a newer docir" answer fresh, in the one process that can afford to.

The CLI must not make a network call: it prints a notice from whatever answer is
cached and stays a tool that works offline and returns in milliseconds. The
daemon has neither constraint — it is already running, and nobody is waiting on
it — so the fetch lives here and the CLI only ever reads the file left behind.

Two details worth keeping:

* **The service decides how often, not this thread.** It skips a fetch when the
  cache was already written today, so a daemon that restarts twenty times in an
  afternoon still asks PyPI once. This loop only has to make sure *something*
  asks.
* **Failures are swallowed**, like the docs watcher's. A release check is a
  courtesy; letting it kill a background thread would leave a daemon that looks
  healthy and has quietly stopped doing one of its jobs.
"""

from __future__ import annotations

import threading

from docir.config.settings import Settings
from docir.modules.release.api import ReleaseService, build_release_service

#: How long to wait before trying again. Well under a day, because the daemon
#: idles out long before then and the *service* is what enforces once-a-day; this
#: only matters for a daemon that happens to live a long time.
_INTERVAL_SECONDS = 6 * 60 * 60


class ReleaseWatcher:
    """A background thread that refreshes the cached latest-release answer."""

    def __init__(self, settings: Settings, service: ReleaseService | None = None) -> None:
        from docir import __version__

        self._service = service or build_release_service(__version__, settings.release_cache_path)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="docir-release", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._refresh()
            self._stop.wait(_INTERVAL_SECONDS)

    def _refresh(self) -> None:
        try:
            self._service.status(refresh=True)
        except Exception as exc:  # a courtesy check must not end the thread
            print(f"[release] check failed: {exc}", flush=True)
