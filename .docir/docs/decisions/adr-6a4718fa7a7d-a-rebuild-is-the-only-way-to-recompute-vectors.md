---
code:
- src/docir/entry_points/dispatch.py
- src/docir/entry_points/cli/app.py
- src/docir/modules/documents/application/services/maintenance_service.py
created: '2026-08-16'
description: 'Retire reindex --embeddings instead of repairing it: it recomputed exactly
  the vectors a rebuild recomputes anyway, for the same time, and skipped both stamps.'
id: adr-6a4718fa7a7d
owner: maintainer
related:
- issue-b24e14474820
- adr-31aa7aa60d11
- adr-ab9c454b760c
status: accepted
tags:
- cli
- embeddings
- persistence
title: A rebuild is the only way to recompute vectors
type: decision
updated: '2026-08-16'
---

## Context

`docir reindex --embeddings` selected a different operation rather than widening
the one it named: it marked every active document dirty, drained the queue, and
returned before the rebuild — writing neither the schema baseline nor the build
stamp. issue-b24e14474820 has the measurement. On this corpus it cost 59 s
against the plain rebuild's 55 s and left `docir check` reporting
`stale-index-build` against a store that had just been reindexed.

The first fix widened it: route the flag through `reindex` so the rebuild still
happens and the stamps are still written, single-writer.

## Decision

Retire the flag instead. A rebuild re-embeds every document it re-saves, so
there was never work for a second mode to do, and `ReindexResult` now reports
`embeddings_recomputed` — which is the part that was actually missing.

## Why widening it was not enough

Widened, the flag's only distinct meaning was `reindex --changed --embeddings`:
rebuild what moved on disk, re-embed everything. That is a real question — the
files did not move, the *reader* did — but it is not worth a flag. Embedding
dominates the runtime, so the combination measured 56 s against a full rebuild's
55 s. It saved a second and offered a second way to be wrong.

The case it was reached for is already covered elsewhere. A vector records the
model that produced it, and `dirty_ids` counts a foreign or NULL `model_id` as
dirty, so `docir embed --flush` recomputes everything after an embedder switch
without a flag (adr-ab9c454b760c). A release that changes *chunking* leaves the
`model_id` intact, and that case is a full rebuild — which is what
`docir self upgrade` already runs.

## Consequences

`docir reindex --embeddings` is now an unknown option and exits non-zero; the
`embeddings` payload key and the MCP parameter are gone. The dispatcher ignores
a leftover key rather than resurrecting the path, which is pinned by a test.

Prose naming the retired flag stays readable — the CLI-conformance guard exempts
it the way it exempts every other verb docir names because it does not exist.
The upgrade instruction is one command, `docir self upgrade`, and that is what
0.14.0's corrected release note says.
