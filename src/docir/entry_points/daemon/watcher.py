"""Keep the derived index current when the files change underneath it.

docir *invites* hand-editing — the README's "what you may edit by hand" table
permits the body, ``docs-schema.yaml`` and ``docs/tags.yaml`` — and then asks
you to remember ``docir reindex``. Until you do, every read path answers from a
stale index: ``get`` returns the old body, the full-text index misses the new
text, the vector is not recomputed, and nothing says so. This closes that
window for anyone running the daemon.

It is safe to do automatically because of the first thesis: the files are
canonical and the index is derived. A reindex only ever makes the index agree
with the files — it writes no markdown, so an automatic one cannot lose work.
That is why this is on by default (``DOCIR_WATCH=0`` opts out) rather than
being a flag someone has to know about.

Two design points worth keeping:

* **The debounce is not decoration.** A ``git checkout`` rewrites hundreds of
  files at once, and one reindex per file would be a stampede.
  :func:`watchfiles.watch` coalesces a burst into a single change set, which is
  exactly the shape this needs.
* **The watcher and the socket server share one executor, and therefore one
  lock.** Requests are serialized by the server loop, but a background reindex
  is a second writer and SQLite has only one. The lock lives in
  :class:`SerializingExecutor`, wrapped once at the composition point so both
  callers necessarily get the same one.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

from watchfiles import Change, DefaultFilter, watch

from docir.config.settings import Settings
from docir.platform.errors import DocirError
from docir.platform.transport.messages import Request, RequestExecutor

#: How long a burst of writes is allowed to settle before one reindex runs.
#: Above an editor's save-and-format cycle, below anything a human waits on.
DEBOUNCE_MS = 400

#: Filenames that are documents even though they are not ``.md``. Only one, but
#: named rather than inlined: `tags.yaml` is the tag registry, a hand-editable
#: canonical file that `reindex` reads, and missing it would leave a renamed tag
#: unindexed while every document that used it reindexed fine.
_CANONICAL_FILES = frozenset({"tags.yaml"})

_MARKDOWN_SUFFIX = ".md"


def is_document(path: str) -> bool:
    """Whether a changed path is one ``reindex`` would actually read.

    The store's own derived files sit outside ``docs/`` (the index lives at the
    home root), so the main job here is ignoring editor scratch files — and
    :class:`DefaultFilter` already covers the common ones. This narrows further
    to what the file store parses, so a stray ``notes.txt`` dropped in the docs
    directory does not trigger a rebuild of the whole corpus.
    """
    name = Path(path).name
    return name in _CANONICAL_FILES or name.endswith(_MARKDOWN_SUFFIX)


class _DocumentFilter(DefaultFilter):
    """``DefaultFilter``'s editor-noise rules, narrowed to canonical files."""

    def __call__(self, change: Change, path: str) -> bool:
        return super().__call__(change, path) and is_document(path)


class DocsWatcher:
    """Reindexes the store when its canonical files change.

    Runs the reindex through a :class:`RequestExecutor` rather than calling the
    maintenance service directly, so the background rebuild is the same
    ``reindex --changed`` a user would run — one command vocabulary, no second
    path that can drift from it.
    """

    def __init__(
        self,
        settings: Settings,
        executor: RequestExecutor,
        *,
        debounce_ms: int = DEBOUNCE_MS,
    ) -> None:
        self._settings = settings
        self._executor = executor
        self._debounce_ms = debounce_ms
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Begin watching on a background thread (no-op if already started)."""
        if self._thread is not None:
            return
        self._settings.ensure_directories()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="docir-docs-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop watching and wait briefly for the thread to notice."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    # -- internals ----------------------------------------------------------

    def _changes(self) -> Iterator[set[tuple[Change, str]]]:
        """The coalesced change batches to react to (seam for tests)."""
        return watch(
            self._settings.docs_root,
            watch_filter=_DocumentFilter(),
            debounce=self._debounce_ms,
            stop_event=self._stop,
        )

    def _run(self) -> None:
        for batch in self._changes():
            if self._stop.is_set():
                break
            self._reindex(len(batch))

    def _reindex(self, changed: int) -> None:
        """Rebuild what moved, and never let a failure kill the watcher.

        A half-written file is normal — an editor saves in two steps — so a
        parse failure here is transient and the *next* batch fixes it. Letting
        that raise would end the thread silently, leaving a daemon that looks
        healthy and has stopped watching, which is worse than a stale index
        because nothing would ever say so.
        """
        request = Request(command="reindex", payload={"changed_only": True})
        try:
            response = self._executor.execute(request)
        except DocirError as exc:
            print(f"[watch] reindex failed: {exc}", flush=True)
            return
        if not response.ok:
            error = response.error or {}
            print(f"[watch] reindex failed: {error.get('message', 'unknown error')}", flush=True)
            return
        data = response.data if isinstance(response.data, dict) else {}
        indexed, removed = data.get("documents_indexed", 0), data.get("documents_removed", 0)
        skipped = data.get("documents_skipped", 0)
        print(
            f"[watch] {changed} file(s) changed -> indexed {indexed}, "
            f"removed {removed}, skipped {skipped}",
            flush=True,
        )
