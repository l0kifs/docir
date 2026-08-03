"""The daemon's docs watcher — the index following the files it derives from.

docir permits hand-editing a body and then asks you to remember `docir reindex`.
Every read between the edit and the reindex answers from a stale index and says
nothing about it. The watcher closes that window, and these tests cover the two
halves separately: what it decides to react to (pure, fast) and whether it
actually reacts (a real daemon, a real file, marked `slow`).

The `_changes` seam exists so the reaction logic is testable without sleeping on
filesystem notifications — a test that waits on inotify timing is a test that
fails on a loaded CI box for reasons that have nothing to do with the code.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from watchfiles import Change

from docir.config.settings import Settings
from docir.entry_points.composition import Container, InProcessExecutor
from docir.entry_points.daemon.watcher import DocsWatcher, is_document
from docir.platform.errors import DaemonError
from docir.platform.transport.messages import (
    Request,
    RequestExecutor,
    Response,
    SerializingExecutor,
)


class TestWhatCounts:
    """Which changed paths are worth a rebuild."""

    @pytest.mark.parametrize(
        "path",
        [
            "/store/docs/decisions/adr-0001-thing.md",
            "/store/docs/tags.yaml",
            "/store/docs/nested/deep/arch-0002.md",
        ],
    )
    def test_canonical_files_trigger(self, path: str) -> None:
        assert is_document(path)

    @pytest.mark.parametrize(
        "path",
        [
            "/store/docs/notes.txt",
            "/store/docs/.DS_Store",
            "/store/index.db",
            "/store/docs/scratch.json",
        ],
    )
    def test_everything_else_is_ignored(self, path: str) -> None:
        """A stray file in docs/ must not rebuild the whole corpus."""
        assert not is_document(path)

    def test_the_tag_registry_is_not_forgotten(self) -> None:
        """`tags.yaml` is canonical and hand-editable but is not markdown.

        Filtering on `.md` alone leaves a renamed tag unindexed while every
        document that used it reindexes fine — a split-brain corpus that
        `check` then reports as unknown tags.
        """
        assert is_document("/store/docs/tags.yaml")


class _RecordingExecutor(RequestExecutor):
    """Captures requests; optionally fails, to prove the thread survives it."""

    def __init__(self, *, fail: Exception | None = None, ok: bool = True) -> None:
        self.requests: list[Request] = []
        self._fail = fail
        self._ok = ok

    def execute(self, request: Request) -> Response:
        self.requests.append(request)
        if self._fail is not None:
            raise self._fail
        if not self._ok:
            return Response(ok=False, error={"message": "boom"})
        return Response(ok=True, data={"documents_indexed": 1, "documents_removed": 0})


class TestReaction:
    def _watcher(self, settings: Settings, executor: RequestExecutor, batches: list) -> DocsWatcher:
        watcher = DocsWatcher(settings, executor)
        watcher._changes = lambda: iter(batches)  # type: ignore[method-assign]
        return watcher

    def test_a_batch_triggers_one_changed_only_reindex(self, settings: Settings) -> None:
        """One reindex per *batch*, not per file — a git checkout is one batch."""
        executor = _RecordingExecutor()
        batch = {(Change.modified, f"/docs/adr-{n}.md") for n in range(200)}
        self._watcher(settings, executor, [batch])._run()

        assert len(executor.requests) == 1
        assert executor.requests[0].command == "reindex"
        assert executor.requests[0].payload == {"changed_only": True}

    def test_each_batch_gets_its_own_reindex(self, settings: Settings) -> None:
        executor = _RecordingExecutor()
        batches = [{(Change.modified, "/docs/a.md")}, {(Change.added, "/docs/b.md")}]
        self._watcher(settings, executor, batches)._run()
        assert len(executor.requests) == 2

    def test_a_failed_reindex_does_not_kill_the_watcher(self, settings: Settings) -> None:
        """A half-written file is normal; the next batch fixes it.

        Letting it raise ends the thread silently, leaving a daemon that looks
        healthy and has stopped watching — worse than a stale index, because
        nothing would ever say so.
        """
        executor = _RecordingExecutor(fail=DaemonError("index is locked"))
        batches = [{(Change.modified, "/docs/a.md")}, {(Change.modified, "/docs/b.md")}]
        self._watcher(settings, executor, batches)._run()
        assert len(executor.requests) == 2, "the watcher stopped after the first failure"

    def test_a_returned_error_does_not_kill_it_either(self, settings: Settings) -> None:
        """Dispatcher errors arrive as a Response, not an exception — both paths."""
        executor = _RecordingExecutor(ok=False)
        batches = [{(Change.modified, "/docs/a.md")}, {(Change.modified, "/docs/b.md")}]
        self._watcher(settings, executor, batches)._run()
        assert len(executor.requests) == 2


class TestSerializingExecutor:
    def test_it_passes_requests_through(self, container: Container) -> None:
        executor = SerializingExecutor(InProcessExecutor(container.dispatcher))
        response = executor.execute(Request(command="ping", payload={}))
        assert response.ok

    def test_calls_do_not_overlap(self) -> None:
        """The property the daemon depends on: one writer at a time.

        SQLite has exactly one, and the watcher is a second caller on another
        thread — without this the background reindex and a client `add` race
        for the write lock.
        """
        import threading

        overlaps = []
        active = []

        class _Slow(RequestExecutor):
            def execute(self, request: Request) -> Response:
                active.append(1)
                overlaps.append(len(active))
                time.sleep(0.02)
                active.pop()
                return Response(ok=True)

        executor = SerializingExecutor(_Slow())
        threads = [
            threading.Thread(target=lambda: executor.execute(Request(command="ping")))
            for _ in range(6)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert max(overlaps) == 1, f"calls overlapped: {overlaps}"


@pytest.mark.slow
class TestEndToEnd:
    """A real daemon, a real hand-edit, no `reindex` command run by anyone."""

    @pytest.fixture
    def store(self, tmp_path, monkeypatch) -> Iterator[Settings]:
        home = tmp_path / "docir"
        monkeypatch.setenv("DOCIR_HOME", str(home))
        monkeypatch.setenv("DOCIR_EMBEDDER", "deterministic")
        monkeypatch.delenv("DOCIR_NO_DAEMON", raising=False)
        settings = Settings.resolve(home=home)
        yield settings
        self._docir(settings, "daemon", "stop", daemon=True)

    def _docir(self, settings: Settings, *args: str, daemon: bool = False) -> str:
        env = {
            "DOCIR_HOME": str(settings.home),
            "DOCIR_EMBEDDER": "deterministic",
            "PATH": __import__("os").environ["PATH"],
        }
        if not daemon:
            env["DOCIR_NO_DAEMON"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "docir", *args],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        return result.stdout

    def test_a_hand_edit_reaches_the_index_without_a_reindex(self, store: Settings) -> None:
        created = json.loads(
            self._docir(
                store,
                "add",
                "--type",
                "decision",
                "--title",
                "Watched decision",
                "--description",
                "Exists to be edited on disk.",
                "--body",
                "The original body.",
            )
        )
        path = Path(store.docs_root) / created["path"]

        # Start the daemon (and its watcher), then edit the file behind its back
        # exactly the way a human would.
        self._docir(store, "daemon", "start", daemon=True)
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "The original body.", "Edited by hand, never reindexed."
            ),
            encoding="utf-8",
        )

        deadline = time.monotonic() + 30
        body = ""
        while time.monotonic() < deadline:
            body = json.loads(self._docir(store, "get", created["id"], daemon=True)).get("body", "")
            if "Edited by hand" in body:
                break
            time.sleep(0.25)

        assert "Edited by hand, never reindexed." in body, (
            "the daemon served a stale body; the watcher did not reindex"
        )
