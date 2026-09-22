---
code:
- src/docir/platform/transport/**
code_baseline:
  src/docir/platform/transport/**: 9c79ebe03425
created: '2026-09-06'
description: A flat reply budget made `docir self upgrade` impossible on a large corpus,
  because the command that always makes docir's most expensive request was bounded
  by a number chosen for an ordinary one.
id: adr-56d29d521620
owner: maintainer
related:
- adr-31aa7aa60d11
- kind: refines
  to: arch-1cfb1b212237
status: accepted
tags:
- daemon
- material
title: The daemon keepalives; the reply timeout bounds silence, not work
type: decision
updated: '2026-09-22'
verified: '2026-09-22'
verified_code:
  src/docir/platform/transport/**: 9c79ebe03425
verified_content: c51cb4e84e20
---

## Context

`docir self upgrade` runs `reindex --resync` through the daemon. After the
package step the index build stamp always differs from the running version — by
construction, that is what the step changed — so the resync is always the *full*
pass, and a full pass marks every document dirty. At the time it also re-embedded
every vector, which made the cost the size of the corpus: 58.4s for 315 documents
and 1,326 vectors on this repository. The drain now skips a document whose inputs
are unchanged, so that price is paid by the release that moves the model or the
chunking rather than by every release — which does not weaken the case below,
since that is still the longest request docir makes, and `build`, `check` and
`embed --flush` were bounded by the same budget.

The client bounded the daemon's reply at a flat `DEFAULT_REQUEST_TIMEOUT` of
300s. So the one command guaranteed to issue the longest request docir can make
was bounded by a budget sized for the shortest. Past roughly 1,500 documents
`self upgrade` could not succeed at all — and it failed *after* replacing the
package, aborting before `agent update` and `check`, while the daemon completed
the rebuild and committed it. What was left was an error, a rebuilt store, stale
instruction files, and no report.

`DOCIR_REQUEST_TIMEOUT` was the documented answer, and it is the wrong shape of
answer: it asks for a prediction of how long a corpus takes to embed, and every
value chosen is wrong for the next corpus.

## Decision

The daemon sends a **keepalive frame** every few seconds while a request runs,
and the client discards keepalives and re-arms the socket on each frame. The
reply timeout therefore measures the gap *between frames* — silence — rather
than the duration of the work.

- A reply is now one or more frames: zero or more keepalives, then exactly one
  response. `keepalive_frame()` and `is_keepalive()` live in the protocol module.
- The daemon runs the request on a worker thread so the handler can keep
  answering. This adds a thread, not a concurrency model: requests already ran
  off the main thread, because the file watcher is a second caller through the
  same `SerializingExecutor`.
- The worker's exception is re-raised on the handler thread rather than turned
  into an `ok=False` response. The connection closing without a reply is what
  tells `SocketExecutor` the daemon is broken and the request is safe to respawn
  and retry; folding a crash into a domain error would delete that signal.
- A client that gives up mid-request stops the keepalives and nothing else. The
  work is one transaction, and abandoning it halfway leaves an index describing
  neither the old corpus nor the new one.

`DaemonTimeoutError` keeps its meaning — the request landed, never resend it —
but now names a wedged or killed daemon. Its message no longer advises raising
the timeout for a large corpus, because that is the one cause that can no longer
produce it.

## Consequences

- No corpus size requires a configuration change. `DOCIR_REQUEST_TIMEOUT`
  remains the knob for "how long before the daemon counts as dead", which is a
  question that can actually be answered.
- The mechanism generalises: `build`, `check` and `embed --flush` were bounded
  by the same budget and are no longer.
- Both ends of a connection always run the same build — the pid file's code
  stamp stops and replaces a mismatched daemon — so the extra frame is not a
  versioned wire concern and needs no negotiation.
- Not fixed here, and fixed since: the resync stamp is the docir *version*, so
  every release re-embedded the whole corpus even when neither the model nor the
  chunking moved. That was a cost problem rather than a correctness one, so it
  was recorded separately and closed on its own (issue-77dd42e3a03a). Each vector
  is now keyed on the model, the embedding text and the chunk triples, and the
  version stamp decides only whether the *metadata* pass is full.
