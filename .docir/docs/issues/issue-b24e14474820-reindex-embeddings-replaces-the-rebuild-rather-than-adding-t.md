---
code:
- src/docir/entry_points/dispatch.py
- src/docir/modules/documents/application/services/maintenance_service.py
created: '2026-08-16'
description: The --embeddings flag re-embeds exactly what a plain reindex already
  re-embeds, for the same time, while skipping the two stamps the rebuild writes —
  so it is dominated by the command it modifies.
id: issue-b24e14474820
owner: maintainer
related:
- adr-31aa7aa60d11
- adr-bd3a820cc57a
- run-f4a756206fe0
- arch-ad342aae8293
status: resolved
tags:
- cli
- embeddings
- release
- material
title: reindex --embeddings replaces the rebuild rather than adding to it
type: issue
updated: '2026-08-16'
---

## The flag is dominated, not complementary

A full `docir reindex` marks every non-archived document dirty and drains the
queue before it returns, so it already recomputes every vector — documents and
chunks. `--embeddings` marks the same documents dirty and drains the same queue,
and does nothing else: no metadata, no FTS, no relations, no id counter, and
neither of the two one-row tables recording how the index was built.

So it is not a cheaper half of the rebuild. It is the same embedding work with
the cheap part removed and the stamps dropped.

## Measured on this corpus

152 documents, `--no-daemon`, warm model:

| Command | Time | Vectors recomputed | Stamps written |
|---|---|---|---|
| `reindex` | 55 s | all 151 | both |
| `reindex --embeddings` | 59 s | all 151 | neither |
| `reindex --changed` | 1.2 s | none | both |

`docir embed --flush` immediately after a full `reindex` returns
`{"embedded":0}` — the queue is already empty. Embedding dominates the runtime,
so the ~1 s of metadata work the flag skips is noise.

## What it costs a reader

Someone who runs it instead of the plain command pays full price and is left
with `docir check` reporting `stale-index-build` against a store they just
rebuilt, which reads as the command having failed. That is how this was found:
the 0.14.0 upgrade note told people to run it, and the note was wrong.

`--changed` passed alongside it is silently ignored — the dispatcher branches on
`embeddings` and returns before reading it. That combination is the one thing in
this area a reader might genuinely want: rebuild only what moved on disk, but
re-embed everything, which is what switching `DOCIR_EMBEDDER` calls for.

## Why the stamps cannot simply be added

Writing `schema_baseline` or `index_build` from the embeddings path would be a
false claim. Both say *the index was rebuilt against this*, and that path
rebuilds no metadata — a store whose schema disabled a type would have the drift
silenced without the rebuild that resolves it. `reindex` being the only writer is
the rule that keeps those two tables honest, and a second writer is not the fix.

The fix is for the flag to route through the rebuild rather than around it.

## Resolution

The flag is gone (adr-6a4718fa7a7d). It was first widened — routed through
`reindex` so the rebuild still ran and both stamps were still written — and that
version measured 56 s against a full rebuild's 55 s. It saved a second and left
a second way to be wrong, so it was retired instead.

`docir reindex --embeddings` now exits non-zero as an unknown option; the
`embeddings` payload key and the MCP parameter are gone, and a leftover key is
ignored rather than reviving the path. What was actually missing shipped in its
place: `ReindexResult.embeddings_recomputed`, and `, N vectors` in the human
output, so a rebuild says out loud that it re-embedded everything it re-saved.

Four guards, each verified by injecting the bug it claims to catch: no reindex
payload can skip the build stamp, a rebuild reports its recomputed vectors,
`--changed` alone recomputes none, and the CLI rejects the retired flag.

The 0.14.0 upgrade note that prompted this was corrected in `CHANGELOG.md` and in
the published release notes: `docir self upgrade` is the whole upgrade.
