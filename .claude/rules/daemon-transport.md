---
paths:
  - "src/docir/entry_points/daemon/**"
  - "src/docir/platform/transport/**"
---

# The daemon and the socket transport

The daemon is a cache for a warm model and a lock for SQLite, nothing else. Every rule here exists because a stale or half-dead daemon imitates a healthy one.

- **The daemon socket path is derived, short, and outside `DOCIR_HOME`** — `Path(tempfile.gettempdir())
  / f"docir-{sha1(home)[:12]}.sock"`. A deep home path would blow past the ~104-char `AF_UNIX` limit,
  so the socket cannot live under it; the hash keeps it stable per installation. The pid and log files
  *do* live under `DOCIR_HOME`.

- **Reaching the socket and waiting for the reply are timed separately, and only one of them
  is retryable.** `_CONNECT_TIMEOUT` (5s, `platform/transport/client.py`) covers the connect;
  a local `AF_UNIX` connect succeeds at once or not at all. The reply is covered by
  `settings.request_timeout` (300s, `DOCIR_REQUEST_TIMEOUT`), because it only arrives after
  the daemon has done the work and one request can be a whole `reindex`. One shared timeout
  meant every command slower than 5s failed while the daemon completed it — `reindex` over
  65 documents takes ~10s. The two failures are then **different exceptions on purpose**: a
  refused connect is a `DaemonError`, the request never landed, and `SocketExecutor` respawns
  and resends it; an unanswered reply is a `DaemonTimeoutError` and is **never** resent,
  because the daemon still has it and the old blanket retry killed it mid-transaction and ran
  the command twice (for `add`, a second document). Do not collapse either pair back together.

- **The daemon watches `docs/` and reindexes what changes, and both halves of that
  are load-bearing.** Hand-editing is *permitted* (the README's by-hand table), so the
  window between an edit and a `reindex` was one where every read answered from a stale
  index and nothing said so. It is safe to automate only because the files are canonical:
  `reindex` writes no markdown, so it can only make the index agree with them — which is
  why it defaults on (`DOCIR_WATCH=0` opts out) rather than being a flag. Two details are
  easy to undo by accident: the watcher and the socket server share **one**
  `SerializingExecutor`, wrapped once in `_run_server`, because the server serializes
  clients but the watcher is a second writer and SQLite has one — two wrappers would each
  be internally consistent and collectively useless. And `DocsWatcher._reindex` swallows
  failures on purpose: a half-written file is normal (editors save in two steps) and the
  next batch fixes it, while an exception would end the thread silently, leaving a daemon
  that looks healthy and has stopped watching. `is_document` includes `tags.yaml`, which
  is canonical and hand-editable but not markdown; filtering on `.md` alone leaves a
  renamed tag unindexed while every document that used it reindexes fine.

- **The daemon is disposable and respawned** by the client (`entry_points/daemon/lifecycle.py`); it
  self-shuts-down after an idle timeout. It is spawned as a detached `python -m docir daemon serve`,
  so `src/docir/__main__.py → entry_points.cli.app:main` and the hidden `daemon serve` command must
  keep working. `daemon serve` builds a container with `background_embeddings=True`.

- **The pid file records a code stamp, and a daemon that does not match is replaced.** A
  daemon loads docir once and lives on, so after an upgrade or an edit to `src/` it kept
  answering from the old code — and a stale answer imitates a correct one (`docir check`
  reported 117 cycles while `--no-daemon` reported 0). `CodeStamp` is `__version__` **plus the
  newest mtime across the package's `.py` files**; the version alone cannot see a source edit,
  since nothing bumps it between commits. `ensure_running` stops and respawns on a mismatch.
  Two details are load-bearing: `current_stamp()` is `@cache`d, because the daemon must report
  the build it *started with*, not what is on disk now; and `stop()` waits for the process to
  exit, because its teardown clears the pid file and unlinks the socket, which a
  freshly-spawned replacement would otherwise lose. A bare-integer pid file (written before
  the stamp existed) reads as an unknown build, which never matches — correctly, that daemon
  predates the check.
