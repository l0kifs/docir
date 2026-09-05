---
paths:
  - "src/docir/modules/documents/application/services/document_service.py"
  - "src/docir/modules/documents/application/services/id_generator.py"
  - "src/docir/modules/documents/domain/entities/document.py"
  - "src/docir/modules/documents/domain/value_objects/identifiers.py"
  - "src/docir/platform/filesystem/markdown_store.py"
  - "src/docir/modules/tags/**"
---

# The document write path

The CLI is the only write path, so every rule these paths break is one nothing else can catch.

- **Ids are allocated from the DB counter (`id_sequences`), never by scanning files** — that is what
  keeps parallel agents from minting the same id. The claim only holds because the counter is
  bumped by **one atomic upsert** (`INSERT … ON CONFLICT DO UPDATE … RETURNING`, raw SQL in
  `repositories.next_number`): a read-modify-write in Python let concurrent `--no-daemon` processes
  all read the same value and return it, so N parallel adds minted one id N times. The daemon hid
  this by serializing requests, so it only ever reproduced in the mode tests and CI use. Keep the
  allocation a single statement. The counter is
  **derived state and `reindex` must restore it**: `_restore_id_sequences` raises each prefix to
  `max(numeric suffix on disk) + 1`, monotonically. Without that, a fresh clone (the index is
  gitignored) re-minted a live id on the next `add`, and the older document — still on disk — fell
  out of every read path. Two backstops guard the same invariant: `IdGenerator` skips a candidate
  already indexed, and a create refuses to write when a file already claims the id
  (`DuplicateDocumentIdError`, keyed on the id rather than the path, since the filename carries the
  title slug). `tests/modules/documents/test_merge_safety.py` pins all three. Conversely, `docir
  check`'s duplicate-id detection
  scans the *files* directly (`MaintenanceService._find_duplicate_ids`), because two files sharing an
  id are invisible in the index (it dedupes by primary key). That scan is the merge-into-`main`
  guard; `docir check --strict` exits 1 for CI.

- **The stale-write guard covers `--replace-body` only, and that is the rule, not an
  oversight.** `update` computes `disk_diverged` (index `content_hash` vs the file's) and
  consults it in one branch. Every edit is applied to the document *as it is on disk*, so a
  metadata patch or a section edit **composes** with an out-of-band change and cannot destroy
  it; `--replace-body` is the only mode that discards the on-disk body, so it is the only one
  where divergence means data loss. Extending the guard would fail writes that lose nothing —
  `--set-title` refusing because someone fixed a typo by hand. Pinned by
  `TestDiskDivergenceScoping`. Note it is a *divergence* check, not optimistic concurrency
  control: no caller supplies a version token, so it cannot see a competing writer (the daemon
  serializes requests; `--no-daemon` parallel writers have a small unguarded window).
  The variable is `disk_diverged`, not `stale` — in this codebase `stale` means a document
  past its review cadence, a different concept on a different clock.

- **Only a content edit may move `updated`.** The reason is no longer staleness: since
  adr-fad49eaa4648 the review clock does not read `updated` at all, and the rule stands on its
  own ground — `updated` is the edit clock every read view shows, so a mechanical rewrite
  claiming the corpus was edited today is a lie about that one. Three write paths rewrite
  documents without touching it: `check --fix`, `delete --force`, and `tag rename` /
  `tag rm --force`. `TagService` therefore has **no `Clock`** — it was injected only to stamp
  the date it must not stamp. Adding a fourth mechanical rewrite? It does not set `updated`.
  What the review clock does read is in `.claude/rules/staleness.md`.

- **A content edit withdraws a standing verification (adr-f4e6ade4afd0).** Same predicate as
  the re-embed (`content_changed`), same transaction: `verified` is erased and `revoked`
  stamped. `--verified` passed with the edit outranks it, and also records
  `verified_content` — the digest of what it covered, taken from the document the write
  produces, never from `base`. `--clear-verified` is the sibling write and not the same one:
  it erases the stamp and leaves *no* `revoked`. A document carrying no verification is left
  alone, and asking to withdraw one it does not have is refused. The argument, and the clock
  both feed, is in `.claude/rules/staleness.md`.

- **A forced delete compensates for the edges it breaks.** `delete --force` strips the edge
  from every referencing document in the same transaction and returns their ids (the CLI
  prints "unlinked from ..."), so it cannot leave a dangling reference — the pattern
  `tag rm --force` already used for tags. It deliberately does **not** advance those
  documents' `updated` — the same rule `check --fix` and the tag paths follow, because a link
  removed from underneath you is not a re-verification.
  Consequence for tests: `delete --force` can no longer manufacture a dangling
  edge, so the `drop_file_of` fixture builds one the way it really arises — remove the
  target's file as a merge would, then `reindex`.

- **`update --type` retypes a document, and every rule about it is load-bearing
  (adr-f8cce745d0d5).** **The id is never re-minted**, prefix included: it is the corpus's
  only address, spelled out in every `related` edge pointing at the document, so a prefix
  records which type *minted* an id and never which type owns it now. Status is validated
  for **membership in the target type**, not as a transition (the type being left has no
  transition graph reaching a different type's), and a status the new type does not declare
  is **refused, not reset** — falling back to `default_status` rewrites every `accepted` in a
  corpus to `draft` and reports success. The existing edges are re-validated against the new
  type even when the call does not supply them, since `allowed_relations` belongs to the
  *source* type and this write persists them. The file moves (`DocumentFileStore.relocate`)
  keeping its **filename** — a retype is not a retitle — and the vacated directory is pruned,
  because `ls docs/` is how a person reads which types a store uses. It is **not** a content
  change: `type` is in `content_hash` but not `embedding_text`, so a corpus-wide rename must
  not queue every document for re-embedding (pinned in `test_embedding_triggers.py`, where
  the recording scheduler makes the decision observable — the inline scheduler drains before
  anything can see it, so an assertion through `embed_flush` passes either way).
  **The source type is never looked up, and that is what keeps the two halves from
  deadlocking**: declaring the replacement type is impossible while the old one holds the
  prefix, and disabling the old one first strands the corpus on an unknown type, so a retype
  that required a known source type would leave hand-editing as the only way through.
