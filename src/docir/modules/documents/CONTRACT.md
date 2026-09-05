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
  At most one body edit mode per call. `append_section` and `replace_section` write the heading
  line themselves, so their text is refused when it *opens* with that same heading — the shape
  `get(section=)` hands back, and the round trip that used to spell a heading twice with no way
  back but `replace_body` (issue-9d4db5cd5f29). `remove_section` is that way back: it deletes a
  heading and everything under it, refuses a `body` passed alongside it rather than ignoring one,
  and resolves a repeated heading to the first
  like every other section operation, so removing the second of two means calling it twice.
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
  `id type status title description tags owner verified revoked created updated archived stale
  code isolated`,
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
- `MaintenanceService.check()` also reports **`empty-index`**, an `error`: the index holds
  nothing while `docs/` holds files, so every structural check below it read a blank graph.
  The only error kind that does not describe damage to the corpus — it means `check` could not
  look, which made `--strict` a merge gate that passed by reading nothing. Unlike
  `stale-index-build`/`schema-drift`, which describe an index that is behind and still answers.
- `MaintenanceService.check() -> [CheckIssue]` — Tier 1 structural findings (incl. staleness,
  and `unknown-type`/`unknown-status`/`unknown-tag`, the three Tier 0 rules a hand-edit can
  bypass, plus `tag-key-format` for a registered key outside the shared grammar). Also
  `missing-required` — a field the type requires that the document does not carry, which the
  schema can start demanding of documents written before it, so no hand-edit need be involved —
  and `unknown-relation-kind`, an edge whose kind the registry no longer lists (permissive when
  the registry is empty, as it is for any schema predating typed edges), and `schema-drift` —
  how the active schema differs from the one the index was last rebuilt against, one finding per
  change.
  `orphan` reads the authored `related` graph **only**, in both directions — as do `dangling`,
  `cycle`, `layering` and the delete guard. No check reads the derived mention graph
  (adr-e98749aa457d): an id named in prose used to clear `orphan`, which made a triage of the
  orphan list close every id on it. A document whose `isolated` reason is non-empty is exempt
  and not reported.
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
- `MaintenanceService.bootstrap() -> ReindexResult` — `reindex()` without the drain, for a
  store that has files and no projection of them. Writes both stamps and leaves every vector
  dirty for the queue, so `embeddings_recomputed` and `vectors_written` are always `0`; the
  composition root calls it while opening such a store and nothing else should. Measured on
  this repository's 191 documents: ~0.9s against ~70s for the drain it defers.
- `index_is_empty(documents=, documents_on_disk=) -> bool` — the one comparison behind
  `check`'s `empty-index` error, `docir doctor`'s finding of the same name, the store
  bootstrap, and the `no document with id` message that names an unbuilt index. Shared, because
  two copies would let one command call a store usable that the other refuses — the drift
  `validation.is_absent` exists to prevent, one size down. False for an empty store: the two
  counts agree at zero.
- `MaintenanceService.store_status() -> StoreStatus` — what the derived index says about
  itself, for `docir doctor` and the `docir_store_status` MCP tool: document count, the
  running version, `stale_index_build`, `schema_drift`, the resolved `embedding_model` and
  how many documents have no current vector for it. `documents` and `documents_on_disk`
  travel as a pair: the index is a projection of the files, so a difference is the
  "reads are answering from stale state" condition stated as a number — which is the only
  way a fresh clone (index gitignored, so absent) is visible once anything has created an
  empty one. Facts, not advice — the judgement is the
  caller's, because only the caller also knows the process it is running in (a daemon serving
  another build, an env var overriding the embedder). Cheap by contract: SQL counts, no
  hydration, no file scan and no graph walk. It says nothing about the corpus; `check()` owns
  that question, and a diagnosis that costs what `check()` costs is one nobody runs while
  something is wrong. `stale_index_build` is carried rather than left to the caller, so the
  version comparison stays implemented once.
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
`UpdateDocumentRequest` also carries `set_owner`, `mark_verified` (stamp the
review clock) and `clear_verified` (withdraw the stamp, refused when none is
standing). The two verification flags are refused together.
`MaintenanceService` requires a `Clock` (staleness needs "today").

`stale` is computed from `Document.stale_reference_date()` — `verified`, else `revoked`, else
`created`, and never `updated` (adr-fad49eaa4648, adr-f4e6ade4afd0). Only `mark_verified` moves an
entry out of the queue; no other write does, and an edit to an unverified document moves
nothing, so recording that an open question is still open cannot silence the report of it
(issue-6726eabcf871). Absent `verified` is not treated as infinitely stale: the cadence still
runs, from `revoked` or `created`.

`revoked` is when a *standing* verification was withdrawn, and both read shapes carry it. Two
writes stamp it, and they are the same operation reached two ways (adr-f4e6ade4afd0):
a content edit stamps it — `set_title`, `set_description`, or any body mode, exactly what
`content_changed` already tracks — because the content somebody read is not the content that is
now there. `mark_verified` in the same call wins and clears `revoked`; a status, type, tag, edge,
owner, `isolated` or `code` change is not a content edit and leaves the verification standing. A
document with no `verified` has nothing to withdraw and is left alone, which is what keeps an
edit from ever moving an unverified document's clock. The digests in `verified_code` are **kept**
across a revocation, so `code-changed` still reports on a document whose calendar has just been
reset.

`clear_verified` is the other half, and it is **not** the same write: it erases the stamp and
leaves *no* `revoked`, so the document ages from `created` as one nobody ever verified does. An
edit says "this was true and the content moved" and earns a restarted cadence; a withdrawal says
"this was never true" and earns nothing — otherwise taking back a stamp that had nearly run out
would push the document's due date further away than leaving it in place. It is refused when no
verification is standing.

`verified_content` is the digest of the title/description/body a verification covered, recorded
by `mark_verified` from the document the write **produces** (so `--replace-section --verified`
covers the section as rewritten) and cleared by both withdrawal paths. `check` compares it and
reports `verification-outdated` — a Tier 1 warning — for a document edited around the CLI: a
hand-edit, a merge, or a build predating revocation. Empty means *unknown*, so a verification
stamped before the field existed reports nothing. Deliberately not `updated`: a status or tag
change moves that without touching a word of what was reviewed.

`isolated` is the reviewed exemption from `orphan`: free text saying why a document is *meant*
to carry no relations, empty meaning not exempt (adr-e98749aa457d). Carried by both read
shapes and by the projection, set by `AddDocumentRequest.isolated` and replaced by
`UpdateDocumentRequest.set_isolated` (`None` leaves it, `""` withdraws the exemption). It is
not an *embedding-relevant* change — no vector reads it — but it is an ordinary edit and stamps
`updated`, as `set_owner` and `mark_verified` do.

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
without recomputing, because a tag rename never touches a body. No Tier 1 check reads it: its
readers are `context` expansion, the `mentions`/`mentioned_by` lists on `get`, and the Tier 2
`unresolved-mention` advisory (adr-e98749aa457d).

## Events published
- none (no event bus; see adr-d3e3616400bf)

## Events consumed
- none

## Owns
- data: document metadata (including `owner`/`verified` stewardship fields, the `isolated`
  exemption reason, and the
  `code` globs a document governs), the
  typed relation graph (each edge carries a `kind`), and the canonical markdown
  files. Physically these live in the shared index/filesystem owned by `platform`
  (grandfathered; see adr-d3e3616400bf).

## Depends on
- modules: indexing (relevance ranking + embedding scheduler)
- platform: persistence, filesystem, embedding, clock, errors, naming (the tag-key grammar)

## Policy
- permissions: none (single-user local CLI; see adr-90e994d931cc)
