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
  `set_type` retypes the document (adr-f8cce745d0d5): the id and its prefix are **not**
  re-minted (the id is the corpus's only address), the file moves to the new type's directory
  keeping its filename, and status, relation whitelist and required fields are all validated
  against the type being *entered*. A status the new type does not declare is refused rather
  than reset, and the source type is never looked up — so a retype is the way out of a type
  `disable_types:` has removed. A retype is not a status transition and not a content change.
- `DocumentService.get(id) -> DocumentView` — one document in full (with body).
  Carries `mentions` / `mentioned_by`: the ids this body names and the documents whose bodies
  name it, resolved against the index. Derived, untyped and unauthored, so they sit beside
  `related` rather than in it — a reader must be able to tell an edge somebody wrote from one
  docir inferred. On `get` only: the list paths are skeletons, and the body these were derived
  from is already in this response. `id` may carry a heading as `<id>#<heading>`, the address
  form `get_many` takes; supplying that and `section` together is refused.
- `DocumentService.get_many([ref]) -> DocumentBatch` — several documents in full, one unit of
  work. The deep read batched, because process start dominates a docir read
  (issue-9509f9fa3631): five `get` calls are five interpreters, and over MCP five model turns.
  It widens how many bodies one *deep* read may name, never which paths carry a body — the
  skeleton contract is untouched. Each ref is `<id>` or `<id>#<heading>`; order is the
  caller's, deduplicated on the whole address (one document under two headings is two reads).
  A ref that does not resolve — no such document, no such heading — lands in
  `DocumentBatch.missing` as `MissingDocument{ref, error}` carrying the error it would have
  raised alone, so one deleted id does not cost the caller the four that resolved. A
  *malformed* ref, and an empty list, still raise: that is the caller's own typo, not a fact
  about the corpus.
- `DocumentService.query(QueryRequest) -> [DocumentSummary]` — structured filtering (skeleton, no body).
  Pages with `limit`/`offset`, applied as a SQL window so the cost of a page does not grow with the
  corpus. `code_paths` answers "which documents govern this file": each path is matched against
  the documents' `code` globs as **text**, so a path the caller just deleted still resolves;
  like `stale_only` it is applied after the query and before the limit. `owner` filters in SQL;
  `stale_only` is derived from the clock and the type's review
  cadence, so it is applied in the service, which means its window is a scan over the filtered set
  rather than a SQL `OFFSET` (the limit counts stale documents, not rows scanned).
- `DocumentService.search(SearchRequest) -> [DocumentSummary]` — full-text search over title,
  description and body (**not** tags); skeleton, no body. `limit`/`offset` are applied after the
  status filter, since FTS5 cannot see a status.
- `QueryRequest.expression` — a JMESPath predicate over each document, applied post-SQL
  **before** the limit like `stale_only` and `code_paths` (adr-7316abc6be93). The projection
  it evaluates against is **public surface**, because a user's expression is written against
  it and cannot be broken silently:
  `id type status title description tags owner verified created updated archived stale code`,
  plus `related` (outgoing) and `related_by` (incoming), each entry `{to, kind, type, status}`
  with the *other* document's type and status resolved — `null` for both when the corpus no
  longer carries it. Adding a key is additive; renaming or removing one is not.
  docir ships no expressions of its own: this is the ability to state a rule, not a rule.
- `DocumentService.context(ContextRequest) -> [DocumentSummary]` — ranked relevant set (skeleton, no body).
  Each ranked hit carries `similarity`, the raw cosine (absolute meaning; `score` is rank-derived RRF
  and has none). `ContextRequest.min_score` is a floor on `similarity`, so an empty result is
  expressible; it does not filter graph-reached neighbours or hits with no current vector.
  `ContextRequest.limit` is a hard ceiling on the response; `ContextRequest.expand`
  (default `DEFAULT_CONTEXT_EXPAND`) is how many of those slots may go to graph-reached
  neighbours, with unused neighbour slots backfilled by ranked hits.
  `ContextRequest.also` carries extra caller-supplied phrasings, retrieved beside `task` and
  fused with it (duplicates dropped, so a repeated string is not two votes). docir writes none
  of them — rewriting belongs at the caller, which is already a model (adr-27c63ad02695).
  `ContextRequest.explain` attaches the retrieval trace to each hit; absent otherwise, since a
  skeleton read must stay cheap.
- `DocumentService.bench(BenchRequest) -> BenchResult` — score the read path against judged
  tasks (`docir bench`). Reports `context`, `context --expand 0` and `search`; the pair is
  what isolates the semantic signal, since graph expansion lifts every embedder. A
  `BenchTask.relevant` entry naming no document is returned under `BenchResult.unresolved`
  and excluded from the judgments — never dropped quietly, because a shrinking recall
  denominator *raises* the score. A task left with no resolvable ids is returned under
  `dropped` and not scored. `StrategyScore.tasks` says how many tasks each mean covered.
- `DocumentService.archive(id)/unarchive(id) -> DocumentView` — toggle active search
- `DocumentService.delete(id, force) -> tuple[str, ...]` — remove file and index rows;
  blocked while referenced unless `force`, which strips the edge from each referencing
  document in the same transaction and returns their ids (without advancing their `updated`)
- `MaintenanceService.reindex(changed_only) -> ReindexResult` — rebuild index from files.
  `changed_only` skips re-saving unchanged files; the removal sweep runs in both modes, so
  either way the index ends up agreeing with the filesystem.
  `ReindexResult.documents_skipped` counts source files that would not parse: the scan is
  best-effort, so a partial rebuild must say so rather than look complete.
  `ReindexResult.embeddings_recomputed` reports the drained queue: a rebuild re-embeds every
  document it re-saves, and never said so — which is what let a "recompute the vectors" mode
  look necessary (adr-6a4718fa7a7d). It counts *documents*; `ReindexResult.vectors_written`
  is the vector count, ~4x larger, and the one that explains the runtime — embedding is ~96%
  of a rebuild and is linear in vectors, not documents.
- `MaintenanceService.resync() -> ReindexResult` — what `docir self upgrade` runs. Reads the
  build stamp and rebuilds in full only when some other version wrote it, since a full pass
  re-embeds everything it re-saves (~96% of the command) and has nothing to recompute on a
  store this build already indexed. Equality against the running version, so a downgrade
  rebuilds too, and an absent stamp rebuilds — unlike `check`'s `stale-index-build`, where
  absent means unknown and stays silent, here unknown means the vectors predate the stamp.
- `MaintenanceService.check() -> [CheckIssue]` — Tier 1 structural findings (incl. staleness,
  and `unknown-type`/`unknown-status`/`unknown-tag`, the three Tier 0 rules a hand-edit can
  bypass, plus `tag-key-format` for a registered key outside the shared grammar). Also
  `missing-required` — a field the type requires that the document does not carry, which the
  schema can start demanding of documents written before it, so no hand-edit need be involved —
  and `unknown-relation-kind`, an edge whose kind the registry no longer lists (permissive when
  the registry is empty, as it is for any schema predating typed edges), and `schema-drift` —
  how the active schema differs from the one the index was last rebuilt against, one finding per
  change.
  `orphan` reads the derived mention graph as well as `related`, so a document linked only by
  someone writing its id in a paragraph is not reported. It is the **only** check that does:
  `dangling`, `cycle`, `layering` and the delete guard read the authored graph alone.
  All warnings: the document stays readable and its edges resolve. Also `unmatched-code` — a
  governed glob that matches nothing — when the service was given a `CodeMatcher`; without one
  (no repository above the store) the finding is skipped rather than reported against a tree
  that does not exist. And `code-changed` — a governed glob whose files differ from what they
  were when somebody last ran `update --verified` — the evidence half of staleness, where
  `stale` is the calendar half. Only patterns carrying a recorded digest are fingerprinted, and
  only for unarchived documents: absent means unverified, never unchanged. A warning and not
  promotable, because a branch that edits code before its docs is the ordinary shape of a change
  and would otherwise fail its own CI. Cleared only by re-reading the document against the code
  and stamping `--verified` — a judgement, which is why `repair()` leaves it; and not by the
  writer that moved the code in the same task, which would be certifying its own change.
- `MaintenanceService.schema_drift() -> [str]` — the same difference as plain lines, for the
  opt-in `DOCIR_SCHEMA_NOTICE` stderr notice and the `docir_schema_drift` MCP tool. Empty when
  nothing moved *or* when the store has no baseline: absent means unknown, not unchanged.
  `reindex` is the only writer of that baseline.
- `MaintenanceService.lint_deep() -> [LintFinding]` — Tier 2 advisory findings
  (`duplicate`, `scope-creep`, `oversized-section`, `ambiguous-heading`,
  `unqualified-section-ref`, `unresolved-mention`); never blocking.
  `unresolved-mention` lists ids a body names that no document carries, one finding per
  document. Tier 2 and not promotable: measured on this repo's corpus, all 47 were
  documentation examples, so a Tier 1 warning would fire only on correct usage.
- `MaintenanceService.flush_embeddings() -> DrainResult` — drain the dirty queue
  (`docir embed --flush`). Both counts, because the caller is reporting to a human who
  just waited for it, and what they waited for was the vectors.
  A vector whose `model_id` no longer matches the active embedder counts as dirty, so this is
  also what recomputes everything after an embedder switch. There is no separate "recompute
  every vector" entry point (adr-6a4718fa7a7d).
- `load_schema(path) -> Schema` — load the per-type document schema. Rejects a status name no
  type declares (transition target, `default_status`, `inactive_statuses` entry), and a
  `required:` entry naming a field no document can carry — both are unsatisfiable, and both are
  reported at load naming what would have worked. `disable_types: [name, ...]` subtracts types
  after the core/profile/inline merge, which is the only way to give up a merged type's **name
  and its prefix** (adr-f8cce745d0d5); it is refused when it names a type the schema does not
  define, one the same file declares inline, or all of them.
- `describe_schema(Schema) -> dict` — the merged schema as plain data (`docir schema show`)
- `check_schema_conformance(Schema, DocumentFileStore) -> ConformanceReport` — what a schema
  costs the corpus, for `docir schema validate` (issue-3678c897295f). Runs
  `GraphChecker.check_schema_conformance` — the four Tier 1 findings a *schema* edit can cause
  (`unknown-type`/`unknown-status`/`missing-required`/`unknown-relation-kind`), which `check`
  calls too so the two cannot disagree. Reads the **files**, not the index, and opens no
  database: a schema edit is a hand edit, which is exactly when the index is behind, and
  `schema validate` must stay reachable for a store too broken to start.
  `ConformanceReport.affected` counts distinct documents, not findings; `documents` and
  `unreadable` are reported always, since "0 findings" over a corpus that would not parse is
  otherwise indistinguishable from a clean one. Advisory: it never changes an exit code.
- `MaintenanceService.repair() -> RepairResult` — fix the mechanically-fixable Tier 1 damage:
  re-issue duplicate ids (oldest file keeps the id) and drop dead `related` edges. `malformed`,
  `unknown-type` and `unmatched-code` each need somebody to read something and decide — what the
  file was meant to say, what the schema should declare, whether the glob is stale or the
  document is — and come back in `RepairResult.remaining`. Does not advance
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
which returns the full `DocumentView`. A ranked hit also carries
`matched_section`: the heading whose vector produced `similarity`, ready to pass
to `get --section`. It is absent for a lexical or graph-reached hit, and for a
document matched by its own vector — the match is real but not addressable as a
section. (Distinct from `DocumentView.section`, which says the body *was*
narrowed to one.) A `related` entry is a typed edge
(`RelatedView{target, kind}`); `AddDocumentRequest.related` /
`UpdateDocumentRequest.set_related` accept `<id>` / `<id>:<kind>` tokens.
`UpdateDocumentRequest` also carries `set_owner` and `mark_verified` (stamp the
review clock). `MaintenanceService` requires a `Clock` (staleness needs "today").

`code` is the repo-relative globs a document declares it governs
(issue-90aea6d1b891). It is carried by both read shapes, set by
`AddDocumentRequest.code` and replaced wholesale by
`UpdateDocumentRequest.set_code` (`None` leaves it, an empty tuple clears it).
Tier 0 validates the **shape only** — absolute paths, `..` segments, backslash
separators and empty entries are refused; a pattern that currently matches
nothing is accepted, because a decision may precede the code it governs.

`mark_verified` also records what each of those globs matched, when the service
was given a `CodeMatcher` (`DocumentService(..., code_matcher=...)`, optional for
the same reason `check`'s is). The digests live in the document's frontmatter,
not the index — unlike the schema baseline and the build stamp, this is the
document's own review state, and a teammate who clones the repo has to see it.
Without a matcher the digests are dropped rather than carried forward: a stale
digest under a fresh `verified` date is the one combination that misreports.
Changing the globs without verifying prunes the digests of the patterns that went
away and keeps the rest. None of this advances `updated` — it is bookkeeping, not
a content edit — and none of it reaches `embedding_text`, so a verification
never queues a re-embed.

`DocumentService.context` expands along mentions as well as authored edges, ordered last and
followed in both directions; `expand_mentions=False` restores the authored-only behaviour and
exists so `benchmarks/mentions.py` can measure the difference (recall@5 0.93 vs 0.84, MRR
unchanged — expansion fills neighbour slots and never displaces a ranked hit).

`mentions` is the derived relation graph — ids one body names in another, stored in the index
and never in frontmatter. `DocumentService`/`MaintenanceService` write it beside every document
save (`Document.mentioned_ids(schema.prefixes())`), `reindex` rebuilds it from the files, and
`UnitOfWork.mentions` reads it. A mention whose target is not indexed is stored and not
returned: a body routinely names a document that does not exist yet, so resolution is a
read-time join rather than a foreign key. Self-mentions are excluded. `tags` writes documents
without recomputing, because a tag rename never touches a body.

## Events published
- none (no event bus; see adr-d3e3616400bf)

## Events consumed
- none

## Owns
- data: document metadata (including `owner`/`verified` stewardship fields and the
  `code` globs a document governs), the
  typed relation graph (each edge carries a `kind`), and the canonical markdown
  files. Physically these live in the shared index/filesystem owned by `platform`
  (grandfathered; see adr-d3e3616400bf).

## Depends on
- modules: indexing (relevance ranking + embedding scheduler)
- platform: persistence, filesystem, embedding, clock, errors, naming (the tag-key grammar)

## Policy
- permissions: none (single-user local CLI; see adr-90e994d931cc)
