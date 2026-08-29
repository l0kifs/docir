---
code:
- src/docir/modules/documents/application/services/document_service.py
created: '2026-08-29'
description: update and get answer 'no document with id' in any checkout whose derived
  index was never built, so the message denies a document that is on disk.
id: issue-e5a0cb196607
owner: maintainer
related:
- issue-87410666c867
- adr-909734bced92
- arch-0368cc754c15
status: resolved
tags:
- cli
- integrity
- material
title: A miss on an unbuilt index reports the document as nonexistent
type: issue
updated: '2026-08-29'
---

**Class:** misleading · **Severity:** material
**Flow:** arch-0368cc754c15 (the write path) · **Step:** `update`'s index lookup
**Frequency:** every read or write naming an existing id in a checkout whose index has not been built

## Finding

`DocumentService.update` and `_require` answer a lookup that misses with
`no document with id '<id>'`, whatever the reason for the miss. Two reasons produce it and
they are undone by opposite actions: the document is gone from the corpus, or the index
answering for it holds nothing. The second is an ordinary state, not a corruption — the index
is derived and gitignored, so a fresh clone and every new `git worktree` start without one,
and nothing on the read or write path builds it.

## What happens today

REPORTED as GitHub issue #7 against 0.17.0, REPRODUCED on 0.21.0:

```
git worktree add ../wt && cd ../wt
docir update <existing-id> --append-section "Notes" --body-file f.txt
  -> error: no document with id '<existing-id>'   (exit 4)
```

`docir get` fails identically. The file is on disk the whole time and `docir reindex` makes
both succeed. The daemon does not rescue it: its watcher reindexes what *changes*, so an
untouched checkout stays in this state indefinitely.

## Impact

The message states a fact about the corpus that is false, so it sends the reader to the wrong
place: a human looks for a deletion that never happened, and an agent — which cannot look at
`docs/` and see the file sitting there — concludes the document is gone. The reporter's
automated workflow gave up a document amendment to it.

`check --strict` and `doctor --strict` have named this condition since 0.20.0 (`empty-index`,
an error, `docir reindex` as the fix — issue-87410666c867, adr-909734bced92). Neither runs on
the path that hits it, so the diagnosis exists in the store's health report and not where
somebody meets the symptom.

## Proposed default

Say which of the two happened, at the point of the miss. The comparison is already shared by
`check` and `doctor` as `index_is_empty(documents=, documents_on_disk=)`; a third reader on
the not-found path costs two counts on the error path and nothing on a lookup that resolves.
Keep the exception type and exit code — the caller's handling should not change, only where
the message sends them — and keep the `no document with id '<id>'` prefix, since the batch
read reports it per reference.

Rebuilding automatically was deferred at first, on a cost estimate that turned out to be
wrong: a rebuild inside an arbitrary command looked corpus-sized. Measured, ~69s of `docir
reindex`'s 70s on this corpus is the embedding drain, and the rebuild alone is ~0.9s against a
0.98s baseline `get`. So opening a store that has files and no index now rebuilds it with the
vectors deferred (adr-e53c813d2f13), and the message is the backstop for what that cannot
reach — an index emptied under a running process, or a store opened by an older build.

## Actors affected

- AI coding agent
- repository maintainer
- automated documentation workflow

## Evidence

- `src/docir/modules/documents/application/services/document_service.py` (`update`, `_require`)
- `src/docir/modules/documents/application/services/maintenance_service.py` (`index_is_empty`)
- https://github.com/l0kifs/docir/issues/7

## Resolution

FIXED, in two parts. Both raise sites go through `DocumentService._not_found`, which consults
`index_is_empty` and appends the diagnosis and `docir reindex` when the index holds nothing
while `docs/` holds files. Same `DocumentNotFoundError`, same exit code 4, same message prefix.
Verified by injecting the bug: with the helper returning the bare message, the empty-index
guards fail while the populated-store guard still passes. Pinned by
`TestMissingIdNamesAnEmptyIndex`.

Then the state itself: `build_container` rebuilds an index it finds empty beside files, so the
message is no longer what a fresh clone or worktree meets first (adr-e53c813d2f13, pinned by
`TestOpeningAStoreWithNoIndexBuildsOne`). `no-index` became a warning in the same change — it
now describes a condition the run reporting it has already undone.
