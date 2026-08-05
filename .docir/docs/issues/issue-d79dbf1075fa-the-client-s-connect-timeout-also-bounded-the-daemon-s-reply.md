---
created: '2026-07-30'
description: The client reported failure for work the daemon completed, then resent
  the request — a write slower than five seconds ran twice.
id: issue-d79dbf1075fa
owner: maintainer
related:
- adr-20eec6e2e2ca
- arch-0a3c2d6d54a6
status: resolved
tags:
- daemon
- blocking
title: The client's connect timeout also bounded the daemon's reply, so any command
  slower than 5s failed
type: issue
updated: '2026-08-05'
---

**Class:** incorrect · **Severity:** blocking
**Flow:** arch-0a3c2d6d54a6 (integrity) · **Step:** any command dispatched over the daemon socket
**Frequency:** every command whose server-side work exceeds 5 seconds — i.e. every `reindex` of a real corpus

## Finding
`DaemonClient.send` called `sock.settimeout(_CONNECT_TIMEOUT)` (5.0s) once, before connecting,
and never changed it. The same budget therefore bounded the reply, which only arrives after the
daemon has finished the work. Separately, `SocketExecutor.execute` caught every `DaemonError`
as "stale socket", called `stop()` and resent the request — so a timed-out write was killed
mid-transaction and then executed a second time.

## What happens today
OBSERVED while migrating docir's own documentation into a 65-document store. `docir reindex`
exited non-zero with `DaemonError: daemon socket error: timed out`; `docir --no-daemon reindex`
completed the identical rebuild in 10.5s, and the daemon had completed it too. Because the
executor retries, the rebuild actually ran twice. On `add` the same path would have produced
two documents for one command.

## Impact
The client reported failure for work the daemon completed, on the command the README tells you
to run after a fresh clone. The retry made it worse than a plain failure: a write slower than
five seconds was executed, reported as failed, and executed again against a daemon killed
mid-transaction. Nothing in the test suite could see it — every fixture corpus answers in
milliseconds, and the daemon tests use `ping` and single `add`s.

## Resolution
FIXED 2026-07-30. Connect and reply are timed separately: `_CONNECT_TIMEOUT` (5s) covers the
connect only, then the socket is re-armed with `settings.request_timeout`
(`DEFAULT_REQUEST_TIMEOUT` 300s, overridable with `DOCIR_REQUEST_TIMEOUT`). A reply timeout now
raises the new `DaemonTimeoutError`, which `SocketExecutor` re-raises instead of retrying, and
whose message names the three escapes (`docir daemon status`, `DOCIR_REQUEST_TIMEOUT`,
`--no-daemon`). Verified by re-injecting both bugs and confirming the three new guards fail:
`test_work_outlasting_the_connect_timeout_still_returns`,
`test_unanswered_request_raises_daemon_timeout` and `test_timeout_is_not_retried`. The original
failing command, `docir reindex` over the 65-document store through the daemon, now succeeds.

## Actors affected
- AI coding agent
- repository maintainer
- CI job

## Evidence
- `src/docir/platform/transport/client.py:20-79`
- `src/docir/entry_points/daemon/socket_executor.py:26-40`
- `src/docir/config/settings.py:28-40`
- `tests/entry_points/test_e2e_daemon.py` (TestReplyTimeoutIsSeparateFromConnect, TestSocketExecutorRetryPolicy)

---

Found by dogfooding: the first docir command ever run against a corpus larger than a test fixture.
