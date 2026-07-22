# documents

## Purpose
Owns the lifecycle of a knowledge document — its content, metadata, and the
links between documents. Every change to a document goes through here so its
files and the derived index never disagree.

## Public operations
- `DocumentService.add(AddDocumentRequest) -> DocumentView` — create a document
- `DocumentService.update(UpdateDocumentRequest) -> DocumentView` — edit metadata and/or body
- `DocumentService.get(id) -> DocumentView` — one document in full
- `DocumentService.query(QueryRequest) -> [DocumentView]` — structured filtering
- `DocumentService.search(SearchRequest) -> [DocumentView]` — full-text search
- `DocumentService.context(ContextRequest) -> [DocumentView]` — ranked relevant set
- `DocumentService.archive(id)/unarchive(id) -> DocumentView` — toggle active search
- `DocumentService.delete(id, force) -> None` — remove file and index rows
- `MaintenanceService.reindex(changed_only) -> ReindexResult` — rebuild index from files
- `MaintenanceService.check() -> [CheckIssue]` — Tier 1 structural findings
- `MaintenanceService.lint_deep() -> [LintFinding]` — Tier 2 advisory findings
- `MaintenanceService.reindex_embeddings()/flush_embeddings() -> int`
- `load_schema(path) -> Schema` — load the per-type document schema

## Events published
- none (no event bus; see ADR-0002)

## Events consumed
- none

## Owns
- data: document metadata, the relation graph, and the canonical markdown files.
  Physically these live in the shared index/filesystem owned by `platform`
  (grandfathered; see ADR-0002).

## Depends on
- modules: indexing (relevance ranking + embedding scheduler)
- platform: persistence, filesystem, embedding, clock, errors

## Policy
- permissions: none (single-user local CLI; see ADR-0003)
