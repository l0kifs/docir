# documents

## Purpose
Owns the lifecycle of a knowledge document — its content, metadata, and the
links between documents. Every change to a document goes through here so its
files and the derived index never disagree.

## Public operations
- `DocumentService.add(AddDocumentRequest) -> DocumentView` — create a document.
  `AddDocumentRequest.doc_id` adopts an existing id instead of allocating (migrating a
  numbered corpus); refused if taken or if the prefix does not match the type, and it
  raises the sequential counter past itself.
- `DocumentService.update(UpdateDocumentRequest) -> DocumentView` — edit metadata and/or body.
  `allow_transition_override` permits an illegal *jump* between declared statuses (never an
  undeclared one); when it actually bypasses a rule, `DocumentView.forced_transition`
  describes it so the caller can warn. Not persisted — no actors to attribute it to.
- `DocumentService.get(id) -> DocumentView` — one document in full (with body)
- `DocumentService.query(QueryRequest) -> [DocumentSummary]` — structured filtering (skeleton, no body).
  Pages with `limit`/`offset`, applied as a SQL window so the cost of a page does not grow with the
  corpus. `owner` filters in SQL; `stale_only` is derived from the clock and the type's review
  cadence, so it is applied in the service, which means its window is a scan over the filtered set
  rather than a SQL `OFFSET` (the limit counts stale documents, not rows scanned).
- `DocumentService.search(SearchRequest) -> [DocumentSummary]` — full-text search over title,
  description and body (**not** tags); skeleton, no body. `limit`/`offset` are applied after the
  status filter, since FTS5 cannot see a status.
- `DocumentService.context(ContextRequest) -> [DocumentSummary]` — ranked relevant set (skeleton, no body).
  Each ranked hit carries `similarity`, the raw cosine (absolute meaning; `score` is rank-derived RRF
  and has none). `ContextRequest.min_score` is a floor on `similarity`, so an empty result is
  expressible; it does not filter graph-reached neighbours or hits with no current vector.
  `ContextRequest.limit` is a hard ceiling on the response; `ContextRequest.expand`
  (default `DEFAULT_CONTEXT_EXPAND`) is how many of those slots may go to graph-reached
  neighbours, with unused neighbour slots backfilled by ranked hits.
- `DocumentService.archive(id)/unarchive(id) -> DocumentView` — toggle active search
- `DocumentService.delete(id, force) -> tuple[str, ...]` — remove file and index rows;
  blocked while referenced unless `force`, which strips the edge from each referencing
  document in the same transaction and returns their ids (without advancing their `updated`)
- `MaintenanceService.reindex(changed_only) -> ReindexResult` — rebuild index from files.
  `changed_only` skips re-saving unchanged files; the removal sweep runs in both modes, so
  either way the index ends up agreeing with the filesystem.
  `ReindexResult.documents_skipped` counts source files that would not parse: the scan is
  best-effort, so a partial rebuild must say so rather than look complete.
- `MaintenanceService.check() -> [CheckIssue]` — Tier 1 structural findings (incl. staleness,
  and `unknown-type`/`unknown-status`/`unknown-tag`, the three Tier 0 rules a hand-edit can
  bypass, plus `tag-key-format` for a registered key outside the shared grammar). All
  warnings: the document stays readable and its edges resolve.
- `MaintenanceService.lint_deep() -> [LintFinding]` — Tier 2 advisory findings
- `MaintenanceService.reindex_embeddings()/flush_embeddings() -> int`
- `load_schema(path) -> Schema` — load the per-type document schema. Rejects a status name no
  type declares (transition target, `default_status`, `inactive_statuses` entry).
- `describe_schema(Schema) -> dict` — the merged schema as plain data (`docir schema show`)
- `MaintenanceService.repair() -> RepairResult` — fix the mechanically-fixable Tier 1 damage:
  re-issue duplicate ids (oldest file keeps the id) and drop dead `related` edges. `malformed`
  and `unknown-type` need a human and come back in `RepairResult.remaining`. Does not advance
  `updated` — a repair is not a re-verification.
- `render_schema_yaml(profiles, id_style) -> str` — a `docs-schema.yaml` body selecting
  `profiles` and a schema-wide `id_style` (`ID_STYLES`: `sequential` | `random`). A type
  without its own `id_style` inherits the schema-wide one; absent both, `DEFAULT_ID_STYLE`
  (`sequential`) applies, so an existing schema keeps minting the ids it always did.
  (defaults to `software`), written by `docir init [--profiles ...]`

## Public constants
- `DEFAULT_SCHEMA_YAML: str` — the bundled default `docs-schema.yaml` body
  (`profiles: [software]` over the frozen core); equals `render_schema_yaml()`.
- `PROFILE_NAMES: tuple[str, ...]` — the bundled schema profile names
  (`software`/`research`/`ops`/`qa`/`legal`), for validating `docir init --profiles`.

The read paths return `DocumentSummary` (frontmatter, tags, typed `related`,
`owner`/`verified`/`stale` — but **no body**); fetch bodies by id with `get`,
which returns the full `DocumentView`. A `related` entry is a typed edge
(`RelatedView{target, kind}`); `AddDocumentRequest.related` /
`UpdateDocumentRequest.set_related` accept `<id>` / `<id>:<kind>` tokens.
`UpdateDocumentRequest` also carries `set_owner` and `mark_verified` (stamp the
review clock). `MaintenanceService` requires a `Clock` (staleness needs "today").

## Events published
- none (no event bus; see ADR-0002)

## Events consumed
- none

## Owns
- data: document metadata (including `owner`/`verified` stewardship fields), the
  typed relation graph (each edge carries a `kind`), and the canonical markdown
  files. Physically these live in the shared index/filesystem owned by `platform`
  (grandfathered; see ADR-0002).

## Depends on
- modules: indexing (relevance ranking + embedding scheduler)
- platform: persistence, filesystem, embedding, clock, errors, naming (the tag-key grammar)

## Policy
- permissions: none (single-user local CLI; see ADR-0003)
