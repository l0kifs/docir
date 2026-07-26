# documents

## Purpose
Owns the lifecycle of a knowledge document — its content, metadata, and the
links between documents. Every change to a document goes through here so its
files and the derived index never disagree.

## Public operations
- `DocumentService.add(AddDocumentRequest) -> DocumentView` — create a document
- `DocumentService.update(UpdateDocumentRequest) -> DocumentView` — edit metadata and/or body
- `DocumentService.get(id) -> DocumentView` — one document in full (with body)
- `DocumentService.query(QueryRequest) -> [DocumentSummary]` — structured filtering (skeleton, no body)
- `DocumentService.search(SearchRequest) -> [DocumentSummary]` — full-text search (skeleton, no body)
- `DocumentService.context(ContextRequest) -> [DocumentSummary]` — ranked relevant set (skeleton, no body).
  `ContextRequest.limit` is a hard ceiling on the response; `ContextRequest.expand`
  (default `DEFAULT_CONTEXT_EXPAND`) is how many of those slots may go to graph-reached
  neighbours, with unused neighbour slots backfilled by ranked hits.
- `DocumentService.archive(id)/unarchive(id) -> DocumentView` — toggle active search
- `DocumentService.delete(id, force) -> None` — remove file and index rows
- `MaintenanceService.reindex(changed_only) -> ReindexResult` — rebuild index from files
- `MaintenanceService.check() -> [CheckIssue]` — Tier 1 structural findings (incl. staleness, unknown type)
- `MaintenanceService.lint_deep() -> [LintFinding]` — Tier 2 advisory findings
- `MaintenanceService.reindex_embeddings()/flush_embeddings() -> int`
- `load_schema(path) -> Schema` — load the per-type document schema
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
- platform: persistence, filesystem, embedding, clock, errors

## Policy
- permissions: none (single-user local CLI; see ADR-0003)
