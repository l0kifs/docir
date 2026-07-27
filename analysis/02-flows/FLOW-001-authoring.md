# FLOW-001 — Capture a decision (the write path)

## Backbone

decide → register vocabulary → author → validate → allocate id → persist file → project into index → embed (deferred)

## Event timeline

| # | Event | Actor | Trigger | Evidence |
|---|-------|-------|---------|----------|
| 1 | TagRegistered | ACT-001/002 | `docir tag add <key> --description` | tag_service.py:43-52 |
| 2 | DocumentRequested | ACT-001/002 | `docir add --type … --title … --description …` | cli/app.py:152-181 |
| 3 | StatusDefaulted | system | no `--status` given | document_service.py:92 |
| 4 | Tier0Validated | system | before any write | validation.py:26-93 |
| 5 | IdAllocated | system | from `id_sequences` counter | id_generator.py:26-40 |
| 6 | FileWritten | system | `docs/<type>s/<id>-<slug>.md` | markdown_store.py:34-39 |
| 7 | IndexProjected | system | same transaction: metadata + FTS + relations | document_service.py:120-123 |
| 8 | EmbeddingMarkedDirty | system | same transaction | document_service.py:122 |
| 9 | EmbeddingComputed | ACT-004 | inline, or debounced 2s in the daemon | scheduler.py:27-44 |
| 10 | DocumentUpdated | ACT-001/002 | `docir update <id> …` | document_service.py:128-159 |
| 11 | DocumentArchived | ACT-001/002 | `docir archive <id>` | document_service.py:161-173 |
| 12 | DocumentDeleted | ACT-001/002 | `docir delete <id> [--force]` | document_service.py:190-206 |

Transaction boundary: events 6–8 commit atomically (one shared UnitOfWork, ADR-0002).
Event 9 is outside it and eventually consistent — the only deferred piece.

**Ordering hazard**: the file write (6) happens *before* the DB commit (7-8). A crash between
them leaves a file on disk that the index does not know about. `reindex` repairs this, but
nothing detects it automatically and no test covers it. → `GAP-013`.

## Hotspots

- **H1** — RESOLVED 2026-07-26. Id allocation read-then-wrote `id_sequences` with no
  serialization guarantee, so it was safe only because the daemon serializes requests
  (CONFIRMED: 6 concurrent `--no-daemon` adds all returned `adr-0002`). Allocation is now one
  atomic upsert, and `docir init` defaults to `id_style: random`, which uses no counter at
  all. → `GAP-009`.
- **H2** — RESOLVED 2026-07-26. `reindex` restored documents, tags, FTS and embeddings but
  not the id counter (CONFIRMED: fresh-clone → reindex → add re-minted a live id). It now
  restores it, and a create refuses to overwrite a file already holding the id. → `GAP-003`.
  One residual: the restore misreads an all-digit random id as sequential → `GAP-041`.
- **H3** — `--override` permits an illegal status transition. Nothing records that an override
  occurred; the resulting document is indistinguishable from a legal one. → `GAP-014`.
- **H4** — `delete --force` removes a document while other documents' *files* keep pointing at
  it. No compensating action. → `GAP-007` (CONFIRMED).
- **H5** — `archive` does not check incoming references at all, though `delete` does. The
  asymmetry is undocumented; the archived doc silently vanishes from graph traversal.
- **H6** — On the `archive`/`unarchive` no-op path the view is built without computing
  staleness, so a stale document reports `stale: false`. → `GAP-015`.
- **H7** — Tier 0 validates `related` only for edges supplied *in this call*. A document that
  already holds a dangling edge can be updated freely and the broken edge is rewritten to the
  canonical file. → `GAP-007` (CONFIRMED by probe).
- **H8** — Two concurrent updates to the same document silently last-write-wins; the
  stale-write guard is computed on every update but consulted only for `--replace-body`.
  → `GAP-037`.
- **H9** — `created`/`updated`/`verified` are local dates with no timezone recorded.
  → `GAP-038` (cosmetic).
- **H10** — No duplicate-content check on `add`. Two identical decisions can be created; only
  the opt-in Tier 2 `lint --deep` mentions it.

## Off-system steps

- **Editing markdown by hand.** The product's second thesis is "agents never edit markdown
  directly", but humans plainly do (the whole point of git-backed files, and `reindex` exists
  "after a hand-edit" — maintenance_service.py:3). A hand-edit that breaks frontmatter is
  silently skipped by `scan()` and surfaces only via `check`'s `malformed` finding. The
  boundary between "canonical file you may edit" and "managed artifact you may not" is
  nowhere stated. → `GAP-016`.
- **Resolving a duplicate id.** No tooling; the user must hand-edit files and reindex.

## Rules

BR-001, BR-002, BR-003, BR-004, BR-005, BR-006, BR-007, BR-008, BR-009, BR-010,
BR-011, BR-012, BR-013, BR-014, BR-015, BR-016, BR-017

## Gaps

GAP-003, GAP-007, GAP-009, GAP-013, GAP-014, GAP-015, GAP-016, GAP-037, GAP-038, GAP-042
