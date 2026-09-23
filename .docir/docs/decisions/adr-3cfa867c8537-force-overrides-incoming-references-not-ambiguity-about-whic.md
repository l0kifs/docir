---
code:
- src/docir/modules/documents/application/services/document_service.py
code_baseline:
  src/docir/modules/documents/application/services/document_service.py: f57b891a1bfb
created: '2026-09-23'
description: Why delete refuses an id more than one file claims whatever flags it
  is given, and why that refusal reads the files rather than the index.
id: adr-3cfa867c8537
owner: maintainer
related:
- issue-6d8c0debc3b9
- issue-bfa5d4331c35
status: proposed
tags: []
title: --force overrides incoming references, not ambiguity about which document is
  meant
type: decision
updated: '2026-09-23'
---

## Decision

`docir delete` refuses an id that more than one file claims, `--force` included, naming the
files. The refusal runs before the unit of work opens, so nothing is read or written on the
way to it.

`--force` overrides **incoming references**. It does not override **ambiguity about which
document is meant**.

## Why the flag cannot cover both

`--force` exists to answer one question: *other documents link to this; strip their edges
anyway*. That is a decision the caller can make, because they can see what they are agreeing
to — the refusal names the citing documents.

An ambiguous id is not that question. The edges `--force` would strip are addressed **by id**,
and both files answer to it, so the caller cannot tell which document's citers they are
agreeing to break. A flag that means "I accept this consequence" cannot be given for a
consequence nobody can state.

## What it was doing instead

Every step of `delete` reads the index, and the index holds one row per id: `reindex` walks
`scan()` in sorted path order and `save` upserts, so the last file wins. So the command

1. acted on **whichever file sorts last**, a choice the caller was never told about;
2. stripped the edge from every document citing the id — including documents that cited the
   file it was *not* deleting, whose frontmatter was rewritten to drop an edge with a live
   target;
3. removed the only index row, leaving the surviving file on disk and invisible to `get`,
   `query` and `context` — while `check --strict` exited **0**, because the duplicate-id scan
   now found one file.

The third is the sharpest: a merge gate that passes on a store with a document nobody can
read. That is [[issue-87410666c867]]'s shape — a check that is green because it read nothing —
arriving through the write path instead of through an empty index.

## Why prevention is the whole fix

Nothing can find the damage afterwards, which was measured rather than assumed:

| moment | what reports it |
|---|---|
| right after the delete | `doctor` → `index-behind-files` (a warning that already existed) |
| after any `reindex` | nothing: `doctor` clean, `check --strict` exit 0 |
| in CI | never — the job runs `reindex` → `doctor --strict` → `check --strict`, healing the index before it looks |
| with the daemon | never — the watcher reindexes on the next change under `docs/` |

And the stripped edge survives all of it. `related: []` is a valid state, indistinguishable
from a document nobody has linked; the only trace is an `orphan` warning that fires on the
ordinary state of a new document. `git log -p` on the citing document is the only recovery,
which is [[adr-e53c813d2f13]]'s thesis earning its keep — the files are canonical, so the
history holds what the index cannot.

So a detection-side finding was considered and rejected: it would fire only between the bad
delete and the next reindex, and every automated path reindexes first.

## Why it reads the files, not the index

The index cannot answer this question by construction. One row per id means the second
claimant is precisely what it has already discarded, so a check against it always reports
exactly one.

`scan()` is the same walk `check` already pays for, and `delete` is a command run by hand a
few times in a corpus's life. A file that does not parse is not a claimant, for the same
reason it is none to the index: `malformed` is the finding that names it.

## Why the same guard is not on `update`

`update` makes the same blind choice — it writes to whichever file the index holds — and is
deliberately left alone.

It costs nothing permanent. Every write keeps the filename, so the rename that could have
clobbered the other claimant cannot be constructed: retitling the established file to exactly
the copy's title leaves the path alone, and `--type` moves one file to another directory and
leaves the other where it is. No edges are stripped, no row is removed, both bodies survive,
and `check` keeps reporting `duplicate-id` as an **error** after every one of them. What
remains is a usability defect: the edit lands on one of two documents and the caller is not
told which.

And the guard is priced for the wrong path. Measured on this store: a warm write is about
1 ms and the scan is 40 ms, so the same refusal would be a 40x tax on the command an agent
runs dozens of times a session — to catch a state that is already an error finding and that
loses nothing. On `delete` the same 40 ms buys prevention of unrecoverable loss on a command
run a handful of times in a corpus's life.

If it is worth closing, the cheap way is to make the answer free rather than to pay for it per
write: `reindex` already walks every file in sorted order and is the one place that *sees*
the collision, so it could record it and every write could read a column. That is a schema
change and belongs in its own decision. Recorded as [[issue-6d8c0debc3b9]], left open.

## Consequences

The repair path is stated by the refusal itself rather than left to be discovered: `docir
check --fix` re-issues all but one id and renames the file to match, which [[issue-bfa5d4331c35]]
confirms works cleanly. Which of the two keeps the id is decided by `(created, path)` and is
arbitrary when both were created the same day — a separate defect, reported as GitHub #22 and
not addressed here.
