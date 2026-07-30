---
created: '2026-07-30'
description: 47 reconstructed business rules with evidence, examples and boundaries;
  every one unconfirmed by a human.
id: ref-32cb4f874fbe
owner: maintainer
related:
- arch-0a3c2d6d54a6
- arch-3e305bc76ff0
- arch-90c90751344f
- arch-ccfcceeb35eb
- arch-f220a644d654
status: active
tags:
- docs
- schema
title: Business rule register — 47 rules, BR-001..BR-074
type: reference
updated: '2026-07-30'
---

# Business rule register

47 rules (BR-001–BR-074, sparsely numbered), reconstructed from code and
tests. Every one is `assumed`: no subject-matter expert confirmed them, so they record
what the system does, not what anybody promised. `pattern` names the rule shape
(unwanted, required, state-driven, …).

## BR-001

**Statement.** When a document is created, the system shall reject the write unless every supplied tag key is already present in the tag registry.

**Pattern:** unwanted · **Flow:** FLOW-001 · **Actor:** AI coding agent · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

- *Given* registry contains {auth} · *when* add --tags auth,security · *then* rejected, UnknownTagError, exit 2; nothing written

**Boundaries:** empty tag list (allowed), tag registered in the same transaction

**Evidence:**
- `src/docir/modules/documents/domain/services/validation.py:51-59`
- `src/docir/modules/documents/application/services/document_service.py:98`

## BR-002

**Statement.** When a document is created, the system shall reject the write unless every `related` target id already exists in the index.

**Pattern:** unwanted · **Flow:** FLOW-001 · **Actor:** AI coding agent · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** Consequence: forward references are impossible. Two documents that reference each other can only be created by adding one, adding the second, then updating the first.

**Evidence:**
- `src/docir/modules/documents/domain/services/validation.py:61-66`

## BR-003

**Statement.** Where the schema registers relation kinds, when an edge is written, the system shall reject any edge whose kind is not registered, and any edge whose kind or target type is outside the source type's `allowed_relations` whitelist.

**Pattern:** complex · **Flow:** FLOW-001 · **Actor:** AI coding agent · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

- *Given* legal profile; obligation type; allowed_relations.implements = [policy, contract] · *when* add --type obligation --related obl-0002:implements · *then* rejected — an obligation may not `implements` another obligation

**Decision table:** {'conditions': ['relation_types_registry', 'kind_registered', 'allowed_relations_for_type', 'target_type_listed'], 'rows': ['[empty, any, any, any] -> allow', '[non-empty, false, any, any] -> reject:UnknownRelationKindError', '[non-empty, true, empty, any] -> allow', '[non-empty, true, kind absent, any] -> reject:DisallowedRelationError', '[non-empty, true, kind present, empty list] -> allow', '[non-empty, true, kind present, listed] -> allow', '[non-empty, true, kind present, not listed] -> reject:DisallowedRelationError', '[non-empty, true, kind present, target id unknown to index] -> allow']}

**Evidence:**
- `src/docir/modules/documents/domain/services/validation.py:68-93`
- `src/docir/modules/documents/domain/schema.py:72-84`

## BR-004

**Statement.** When no status is given at creation, the system shall assign the type's `default_status`.

**Pattern:** event · **Flow:** FLOW-001 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Evidence:**
- `src/docir/modules/documents/application/services/document_service.py:92`
- `src/docir/modules/documents/infra/profiles.py:29`

## BR-005

**Statement.** While a document is at status S, when a change to status T is requested, the system shall permit it only if T is reachable from S in the type's transition map, unless the caller passes `--override`, in which case only T's membership in the status enum is checked.

**Pattern:** complex · **Flow:** FLOW-001 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

- *Given* decision at 'rejected' (a terminal status) · *when* update --status accepted --override · *then* allowed; the document is now 'accepted' with no record that a rule was bypassed

**Decision table:** {'conditions': ['target_in_enum', 'transition_declared', 'override_flag'], 'rows': ['[false, any, false] -> reject:InvalidStatusError', '[false, any, true] -> reject:InvalidStatusError', '[true, true, any] -> allow', '[true, false, false] -> reject:InvalidStatusTransitionError', '[true, false, true] -> allow, UNAUDITED', '[S == T, any, any] -> allow (self-loop always permitted)']}

**Open questions:** Q-014

**Evidence:**
- `src/docir/modules/documents/application/services/document_service.py:324-329`
- `src/docir/modules/documents/domain/schema.py:66-70`

## BR-006

**Statement.** The system shall allocate every document id itself and shall never accept a caller-supplied id: a `sequential` type draws from a per-prefix counter in the index, a `random` type mints a hex token and retries on collision.

**Pattern:** complex · **Flow:** FLOW-001 · **Actor:** — · **Confidence:** observed · **Status:** confirmed · **Owner:** repo maintainer

**Notes:** Restated 2026-07-26. The original wording ("from a per-prefix counter") described only the sequential path and read as though the counter were the sole mechanism — which is what made BR-007's uniqueness claim look safe when it was not.

**Evidence:**
- `src/docir/modules/documents/application/services/id_generator.py:26-48`
- `src/docir/platform/persistence/repositories.py:48-66`
- `src/docir/modules/documents/domain/value_objects/identifiers.py:40-48`

## BR-007

**Statement.** The system shall issue a unique id to each document.

**Pattern:** ubiquitous · **Flow:** FLOW-001 · **Actor:** — · **Confidence:** observed · **Status:** confirmed · **Owner:** repo maintainer

- *Given* a store with adr-0001, adr-0002 on disk and no index (fresh clone) · *when* docir reindex && docir add --type decision --title 'Third' · *then* OBSERVED: the new document is issued adr-0001; adr-0001 'First' becomes invisible to get/query/search/context while its file remains on disk

**Notes:** RESOLVED 2026-07-26 — held now, was not when first written. Both violations are fixed (GAP-003, GAP-009) and `docir init` defaults to `id_style: random`, which removes the counter from the picture entirely for new stores. Original finding, kept for the record: CLAUDE.md said "Ids are allocated from the DB counter (SequenceRow), never by scanning files — that is what keeps parallel agents from minting the same id." Two confirmed violations: (a) --no-daemon concurrency: 6 simultaneous adds all returned adr-0002 (GAP-009); (b) reindex loses the counter, so the next add re-mints a live id (GAP-003). Uniqueness is actually provided by the daemon's single-connection serialization plus a counter that survives, not by the counter itself.

**Open questions:** Q-001, Q-002

**Evidence:**
- `CLAUDE.md`
- `src/docir/modules/documents/application/services/id_generator.py:3-5`

## BR-008

**Statement.** When a document is written, the system shall persist the markdown file and update the metadata, full-text and relation projections such that either all of them reflect the write or none do.

**Pattern:** event · **Flow:** FLOW-001 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** Holds for the three index projections (one UoW). Does NOT hold across the file/DB boundary: the file is written before the commit, so a crash in between leaves an unindexed file. → GAP-013.

**Evidence:**
- `src/docir/modules/documents/application/services/document_service.py:118-123`
- `docs/adr/ADR-0002-shared-derived-index.md`

## BR-009

**Statement.** When a document's title, description or body changes, the system shall mark its embedding stale and recompute it off the critical path; the command shall return before the recompute completes unless `--wait-embeddings` is given.

**Pattern:** event · **Flow:** FLOW-001 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Boundaries:** metadata-only change → embedding NOT marked dirty (correct: tags/status are not in embedding_text)

**Evidence:**
- `src/docir/modules/documents/application/services/document_service.py:153-158`
- `src/docir/modules/indexing/infra/scheduler.py:105-115`

## BR-010

**Statement.** If a delete is requested for a document other documents reference, then the system shall refuse it and name the referencing documents, unless `--force` is given.

**Pattern:** unwanted · **Flow:** FLOW-001 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

- *Given* adr-0001 related: [issue-0001] · *when* docir delete issue-0001 --force · *then* OBSERVED: issue-0001 gone; adr-0001's file still reads `related: [issue-0001]`; `docir check` reports dangling; `docir update adr-0001 --set-title X` succeeds and rewrites the broken edge back to disk

**Notes:** With --force the referencing documents' files keep the now-broken id. No compensating action exists, and no later write repairs it. → GAP-007.

**Open questions:** Q-007

**Evidence:**
- `src/docir/modules/documents/application/services/document_service.py:194-200`

## BR-011

**Statement.** If `--replace-body` is requested without `--force`, or when the file changed on disk since it was indexed, then the system shall refuse the write.

**Pattern:** unwanted · **Flow:** FLOW-001 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** The stale-write guard protects ONLY `--replace-body`. `--append-section` and `--replace-section` apply to the on-disk version, so they are safe by construction; a metadata-only patch silently absorbs an out-of-band body edit into the index.

**Evidence:**
- `src/docir/modules/documents/application/services/document_service.py:369-380`

## BR-012

**Statement.** If more than one body-edit mode is supplied in one call, then the system shall reject the request.

**Pattern:** unwanted · **Flow:** FLOW-001 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Evidence:**
- `src/docir/modules/documents/application/services/document_service.py:353-359`

## BR-013

**Statement.** When an update would change nothing, the system shall return the current document unchanged and shall not advance `updated`.

**Pattern:** event · **Flow:** FLOW-001 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Evidence:**
- `src/docir/modules/documents/application/services/document_service.py:142-143`

## BR-014

**Statement.** When a document is archived, the system shall remove it from full-text and semantic retrieval while retaining its file, its metadata row and its relation edges.

**Pattern:** event · **Flow:** FLOW-001 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** Unlike delete, archive does not consider incoming references at all.

**Evidence:**
- `src/docir/modules/documents/application/services/document_service.py:161-173`

## BR-015

**Statement.** The system shall fix a document's file path at creation from its id and title slug, and reuse that path for every later write.

**Pattern:** ubiquitous · **Flow:** FLOW-001 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** Consequence: renaming a document's title leaves the old slug in the filename forever. Deliberate (avoids orphaning renamed files) and undocumented for users. Also the mechanism by which the GAP-003 collision produces two files rather than an overwrite.

**Evidence:**
- `src/docir/platform/filesystem/markdown_store.py:34-39`
- `87-89`

## BR-016

**Statement.** The system shall record an edge as at most one kind per ordered (source, target) pair; if a source lists the same target twice, the last kind shall win.

**Pattern:** ubiquitous · **Flow:** FLOW-001 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** Silent last-wins deduplication; no warning that an edge was discarded.

**Evidence:**
- `src/docir/platform/persistence/repositories.py:81-85`
- `src/docir/platform/persistence/alembic/versions/0002_typed_edges_and_staleness.py:32-35`

## BR-017

**Statement.** When an edge of the default kind (`relates_to`) is written to disk, the system shall render it as a bare id, and any other kind as a `{to, kind}` mapping.

**Pattern:** event · **Flow:** FLOW-001 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Evidence:**
- `src/docir/platform/filesystem/markdown_store.py:156-168`
- `docs/adr/ADR-0005-typed-relation-edges.md`

## BR-018

**Statement.** If a read limit of zero or less is requested, then the system shall reject the request.

**Pattern:** unwanted · **Flow:** FLOW-002 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Boundaries:** limit = 0 rejected, limit = 1 allowed, limit = -1 rejected, limit above corpus size: allowed, returns everything

**Evidence:**
- `src/docir/modules/documents/application/services/document_service.py:55-63`

## BR-025

**Statement.** When ranked context is requested, the system shall combine a full-text ranking with a semantic ranking by reciprocal rank fusion and order results by the fused score.

**Pattern:** event · **Flow:** FLOW-002 · **Actor:** AI coding agent · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** RRF is rank-based, so the emitted `score` carries no absolute meaning and is not comparable across queries. It is published in the README's agent-facing example (README:90) with no interpretation given. → GAP-017.

**Evidence:**
- `src/docir/modules/indexing/domain/scoring.py:44-73`
- `src/docir/modules/documents/application/services/document_service.py:256-258`

## BR-026

**Statement.** The system shall consider at most 25 full-text candidates when fusing rankings.

**Pattern:** ubiquitous · **Flow:** FLOW-002 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** Unexplained magic constant, not configurable, not derived from `limit`. A document ranked 26th lexically can only enter via the semantic side.

**Evidence:**
- `src/docir/modules/documents/application/services/document_service.py:47`

## BR-027

**Statement.** The list read paths (`query`, `search`, `context`) shall return frontmatter, typed edges and a staleness flag, and shall never return a document body.

**Pattern:** ubiquitous · **Flow:** FLOW-002 · **Actor:** AI coding agent · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Evidence:**
- `src/docir/modules/documents/application/dto.py:84-108`
- `README.md:103-106`

## BR-028

**Statement.** While a document is archived, the system shall exclude it from `query`, `search` and `context` unless `--include-archived` is given; `get` shall return it regardless.

**Pattern:** state · **Flow:** FLOW-002 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** `search` has no --include-archived flag at all; it relies on archived docs being absent from the FTS table. Reaching the same outcome by a different mechanism.

**Evidence:**
- `src/docir/platform/persistence/repositories.py:115-116`
- `src/docir/modules/documents/application/services/document_service.py:210-214`

## BR-029

**Statement.** While a document's status is one of its type's `inactive_statuses`, the system shall exclude it from the list read paths unless `--include-resolved` is given.

**Pattern:** state · **Flow:** FLOW-002 · **Actor:** — · **Confidence:** observed · **Status:** disputed · **Owner:** repo maintainer

- *Given* issue-0001 status=resolved, referenced by adr-0001 · *when* docir context auth --limit 5 (no --include-resolved) · *then* OBSERVED: issue-0001 returned with status resolved, via_graph true. The same document is correctly hidden by `search` and `query`.

**Notes:** STATED but NOT HELD on one of four paths. `context`'s graph-expansion step checks `archived` but not inactive status, so a resolved issue is returned without the flag.

**Open questions:** Q-005

**Evidence:**
- `src/docir/modules/documents/application/services/document_service.py:242`
- `267-268`
- `src/docir/platform/persistence/repositories.py:117-118`

## BR-030

**Statement.** When ranked context is returned, the system shall additionally include every document reachable in one hop along the selected documents' outgoing edges.

**Pattern:** event · **Flow:** FLOW-002 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

- *Given* 3 decisions each with 2 outgoing edges, all ranking above the cut · *when* docir context 'cache invalidation policy' --limit 3 · *then* OBSERVED: 9 documents returned

**Notes:** Applied AFTER the limit is enforced and itself uncapped, so `--limit N` does not bound the response. OBSERVED: --limit 3 returned 9. Incoming edges are never followed, so "what superseded this?" is not answerable from the superseded document. → GAP-005, GAP-019.

**Open questions:** Q-003

**Evidence:**
- `src/docir/modules/documents/application/services/document_service.py:297-307`

## BR-031

**Statement.** The system shall always return the requested number of context results when the corpus is non-empty, regardless of how well any document matches.

**Pattern:** ubiquitous · **Flow:** FLOW-002 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

- *Given* a store containing only 'Postgres connection pooling' · *when* docir context 'how do I bake sourdough bread' --limit 3 · *then* OBSERVED: returns the Postgres decision, score 0.0328

**Notes:** An emergent rule nobody wrote: every active vector is ranked, so the fused list is never empty and there is no similarity floor. "Nothing relevant" is not an expressible answer.

**Open questions:** Q-009

**Evidence:**
- `src/docir/modules/indexing/domain/scoring.py:36-42`
- `src/docir/modules/documents/application/services/document_service.py:257`

## BR-032

**Statement.** When free text is searched, the system shall match documents containing ANY of the query terms.

**Pattern:** event · **Flow:** FLOW-002 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** OR-of-terms, not AND, and not a phrase. A three-word query matches a document sharing one common word. Undocumented; `docir search` is presented as plain "full-text search". Also means punctuation-only or stopword-only queries return nothing at all (empty MATCH).

**Boundaries:** empty query → no results, not an error, query of only punctuation → no results

**Evidence:**
- `src/docir/platform/persistence/repositories.py:352-357`

## BR-033

**Statement.** While a document's type declares a review cadence, the system shall report it as stale once more days have elapsed since its last verification (or last edit, if never verified) than the cadence allows.

**Pattern:** state · **Flow:** FLOW-002 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Boundaries:** exactly at cadence → NOT stale (strict >), cadence 0 → never stale, archived → never stale, unknown type → never stale

**Notes:** Falling back to `updated` means any edit — including an administrative tag rename — resets the clock. → GAP-020.

**Evidence:**
- `src/docir/modules/documents/domain/services/graph_checks.py:84-111`
- `src/docir/modules/documents/domain/entities/document.py:73-75`
- `docs/adr/ADR-0006-staleness-as-data.md`

## BR-034

**Statement.** When output is captured (stdout is not a terminal) or `--json` is given, the system shall emit compact JSON with information-free fields omitted; at a terminal it shall render tables.

**Pattern:** complex · **Flow:** FLOW-002 · **Actor:** AI coding agent · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Decision table:** {'conditions': ['pretty_flag', 'json_flag', 'stdout_is_tty', 'no_trim_flag'], 'rows': ['[true, any, any, any] -> rich tables', '[false, true, any, false] -> compact trimmed JSON', '[false, true, any, true] -> compact full JSON', '[false, false, true, any] -> rich tables', '[false, false, false, false] -> compact trimmed JSON', '[false, false, false, true] -> compact full JSON'], 'notes': '--no-trim has no effect on the table path. Precedence is identical for --help, which is resolved from argv because Click renders it before CliState exists (runner.py:51-66).\n'}

**Notes:** An omitted key always means the field's default, never a real zero or false.

**Evidence:**
- `src/docir/entry_points/cli/rendering.py:27-57`
- `README.md:85-95`

## BR-041

**Statement.** When the index is rebuilt, the system shall reconstruct it from the markdown files and the tag registry file, which are canonical.

**Pattern:** event · **Flow:** FLOW-003 · **Actor:** — · **Confidence:** observed · **Status:** disputed · **Owner:** repo maintainer

**Notes:** INCOMPLETE. `id_sequences` is part of the index and is not reconstructed, so the rebuild is not faithful. This is the mechanism behind GAP-003. Also: malformed files are skipped silently and not counted (GAP-022); `--changed` skips the removal sweep so deleted files stay indexed (GAP-021).

**Open questions:** Q-001

**Evidence:**
- `src/docir/modules/documents/application/services/maintenance_service.py:58-69`
- `README.md:34`

## BR-042

**Statement.** When structural checks run, the system shall report unknown types, dangling references, relation cycles, orphans, layering violations, staleness, duplicate ids and malformed files as non-blocking findings.

**Pattern:** event · **Flow:** FLOW-003 · **Actor:** CI job · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Evidence:**
- `src/docir/modules/documents/domain/services/graph_checks.py:44-58`
- `src/docir/modules/documents/application/services/maintenance_service.py:84-124`

## BR-043

**Statement.** If `--strict` is given and any finding of any kind exists, then the system shall exit with code 1.

**Pattern:** unwanted · **Flow:** FLOW-003 · **Actor:** CI job · **Confidence:** observed · **Status:** disputed · **Owner:** repo maintainer

- *Given* a fresh store with two unrelated documents and no other problems · *when* docir check --strict · *then* OBSERVED: exit 1, from two `orphan` findings

**Notes:** All eight finding kinds are equal. `orphan` fires for any document with no relations — the default state of a new document — so the gate fails on a healthy corpus. There is no severity, no kind selection and no ignore mechanism, so the only way to keep CI green is to abandon the gate, which also abandons duplicate-id detection: the gate's stated purpose.

**Open questions:** Q-004

**Evidence:**
- `src/docir/entry_points/cli/app.py:439-440`

## BR-044

**Statement.** When duplicate ids are looked for, the system shall scan the markdown files directly rather than the index, because the index deduplicates by primary key.

**Pattern:** event · **Flow:** FLOW-003 · **Actor:** git / branch merge · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** Correct and load-bearing. Note what it implies: when two files share an id the index silently keeps one and drops the other, so the other document is invisible to every read path while its file still exists. That is the actual damage in GAP-003 and GAP-009.

**Evidence:**
- `src/docir/modules/documents/application/services/maintenance_service.py:109-124`

## BR-045

**Statement.** While a relation points from a higher-level type to a lower-level one and its kind is neither `supersedes` nor `contradicts`, the system shall report a layering violation.

**Pattern:** state · **Flow:** FLOW-003 · **Actor:** — · **Confidence:** observed · **Status:** disputed · **Owner:** repo maintainer

- *Given* software profile; adr-0001 related: [issue-0003] · *when* docir check · *then* OBSERVED: layering violation: decision 'adr-0001' depends on lower-level issue

**Notes:** In the default `software` profile decision=3 and issue=1, so linking a decision to the issue that motivated it — the pairing in the README's own example output — is a permanent violation. Either the levels, the exempt-kind list, or the rule is wrong.

**Open questions:** Q-006

**Evidence:**
- `src/docir/modules/documents/domain/services/graph_checks.py:194-223`
- `src/docir/modules/documents/domain/services/graph_checks.py:26`

## BR-046

**Statement.** When advisory linting is requested with `--deep`, the system shall report document pairs whose embeddings exceed 0.9 cosine similarity, and documents whose body exceeds 8000 characters.

**Pattern:** event · **Flow:** FLOW-003 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** Both thresholds are unexplained constants and neither is configurable. The duplicate scan is O(n²) over all active vectors with no cap. 8000 chars is ~2000 tokens — well under a normal ADR for a complex decision.

**Evidence:**
- `src/docir/modules/documents/domain/services/similarity_lint.py:29-69`

## BR-047

**Statement.** When embeddings are recomputed, the system shall drop any queued entry whose document no longer exists, so a deleted document cannot wedge the queue.

**Pattern:** event · **Flow:** FLOW-003 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Evidence:**
- `src/docir/modules/indexing/infra/scheduler.py:36-39`

## BR-059

**Statement.** The system shall resolve its store as, in order: an explicit `--home`, then `DOCIR_HOME`, then the nearest `.docir` directory found by walking up from the working directory, then a global `~/.docir`.

**Pattern:** ubiquitous · **Flow:** FLOW-004 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** The last fallback is silent. A command run in a repo that was never initialised writes into the user's home store with no indication. → GAP-023.

**Boundaries:** nested .docir directories → nearest wins, DOCIR_HOME set to empty string → treated as unset

**Evidence:**
- `src/docir/config/settings.py:76-104`
- `docs/adr/ADR-0009-per-project-store.md`

## BR-060

**Statement.** Where a schema file names profiles, the system shall merge the frozen core, then each named profile in order, then the file's own inline definitions, with later fragments replacing whole types of the same name.

**Pattern:** optional · **Flow:** FLOW-004 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** Replacement is whole-type, not field-level; overriding one attribute of a bundled type means restating all of it. Silent — no warning that a type was replaced.

**Boundaries:** no `profiles:` key → inline-only, core NOT merged, relation kinds unconstrained, `profiles: []` → core only, all five profiles → 15 types, no prefix collision (verified)

**Evidence:**
- `src/docir/modules/documents/infra/schema_loader.py:88-117`
- `docs/adr/ADR-0007-core-plus-profiles.md`

## BR-061

**Statement.** If a schema declares a duplicate type prefix, a default status outside its own status enum, or an `allowed_relations` kind absent from the relation registry, then the system shall refuse to load it.

**Pattern:** unwanted · **Flow:** FLOW-004 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

- *Given* type ticket: statuses {open: [closd], closed: []}, inactive_statuses [done] · *when* docir schema validate · *then* OBSERVED: {"valid":true}. At write time: `invalid transition 'open' -> 'closed'` — which names a status that IS declared, misdirecting the reader away from the typo in the schema. `open` has no reachable exit.

**Notes:** These three are checked. Transition targets and `inactive_statuses` are NOT checked for membership in the status enum, so a type can declare an unreachable exit and still validate. → GAP-010.

**Open questions:** Q-010

**Evidence:**
- `src/docir/modules/documents/domain/schema.py:97-117`

## BR-062

**Statement.** When a store is initialised, the system shall write a schema file and a `.gitignore` covering the derived index, preserving existing files unless `--force` is given.

**Pattern:** event · **Flow:** FLOW-004 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** `--force` overwrites the schema and the .gitignore together, with no separate control, no confirmation and no backup. → GAP-026.

**Evidence:**
- `src/docir/entry_points/composition.py:182-192`

## BR-063

**Statement.** When agent instructions are installed, the system shall write only files it owns, and shall modify a pre-existing `AGENTS.md` only within its own marker block.

**Pattern:** event · **Flow:** FLOW-004 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Evidence:**
- `src/docir/modules/agents/application/service.py:110-135`
- `docs/adr/ADR-0008-agent-instruction-scaffolding.md`

## BR-064

**Statement.** If an unrecognised agent target name is requested, then the system shall ignore it.

**Pattern:** unwanted · **Flow:** FLOW-004 · **Actor:** — · **Confidence:** observed · **Status:** disputed · **Owner:** repo maintainer

- *Given* a project directory · *when* docir agent install --agent claud · *then* OBSERVED: prints [], exit code 0, writes nothing. The user believes their agent is configured.

**Notes:** This is the behaviour, not a defensible rule. Silent no-op on a typo in a once-per-repository onboarding command. Contrast `docir init --profiles`, which raises SchemaError naming the available profiles (composition.py:177-180) — the same class of input, handled correctly two files away.

**Open questions:** Q-011

**Evidence:**
- `src/docir/modules/agents/application/service.py:96-98`

## BR-069

**Statement.** When a tag is renamed or force-removed, the system shall rewrite every referencing document's file and index row within the same transaction.

**Pattern:** event · **Flow:** FLOW-005 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** Also sets `updated = today` on each, which resets the staleness clock for any document without an explicit `verified` date. → GAP-020.

**Evidence:**
- `src/docir/modules/tags/application/services/tag_service.py:62-105`

## BR-070

**Statement.** If a tag removal is requested while documents still carry the key, then the system shall refuse and name them, unless `--force` is given.

**Pattern:** unwanted · **Flow:** FLOW-005 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Evidence:**
- `src/docir/modules/tags/application/services/tag_service.py:90-96`

## BR-071

**Statement.** If a tag is registered under a key that already exists, then the system shall refuse it.

**Pattern:** unwanted · **Flow:** FLOW-005 · **Actor:** — · **Confidence:** observed · **Status:** assumed · **Owner:** repo maintainer

**Notes:** The same check blocks renaming a tag onto an existing key, so merging two tags is impossible. → GAP-028.

**Evidence:**
- `src/docir/modules/tags/application/services/tag_service.py:46-47`

## BR-073

**Statement.** Where a schema declares a top-level `id_style`, the system shall apply it to every type the merged schema contains, including those contributed by the core and by profiles, unless a type declares its own.

**Pattern:** optional · **Flow:** FLOW-004 · **Actor:** — · **Confidence:** observed · **Status:** confirmed · **Owner:** repo maintainer

**Boundaries:** no id_style anywhere -> DEFAULT_ID_STYLE (sequential), so a pre-existing docs-schema.yaml keeps minting the ids it always did, schema-wide random + per-type sequential -> that one type stays sequential, unknown value -> SchemaError at load, exit 3

**Notes:** `docir init` writes this key explicitly (default `random`); the resolution happens before any type is parsed, which is what lets one line cover profile-contributed types.

**Evidence:**
- `src/docir/modules/documents/infra/schema_loader.py:105-121`
- `src/docir/modules/documents/infra/schema_loader.py:134-146`
- `src/docir/modules/documents/domain/schema.py:34-42`

## BR-074

**Statement.** When a store is initialised, the system shall write a collision-resistant `random` id style unless the caller asks for `sequential`.

**Pattern:** event · **Flow:** FLOW-004 · **Actor:** — · **Confidence:** observed · **Status:** confirmed · **Owner:** repo maintainer

- *Given* an empty project directory · *when* docir init . · *then* docs-schema.yaml carries `id_style: random`; the first decision is adr-eb7ce81f8cd0 (OBSERVED)
- *Given* the same · *when* docir init . --id-style sequential · *then* the first decision is adr-0001 (OBSERVED)

**Notes:** Deliberately differs from DEFAULT_ID_STYLE. `init` scopes docs to a *shared repository*, where two branches can each mint adr-0007; the bare `~/.docir` fallback is a single-user scratch store where readable numbers cost nothing.

**Evidence:**
- `src/docir/entry_points/composition.py:50-56`
- `src/docir/entry_points/cli/app.py:95-140`

## BR-072

**Statement.** The system shall accept any non-empty string as a tag key.

**Pattern:** ubiquitous · **Flow:** FLOW-005 · **Actor:** — · **Confidence:** inferred · **Status:** assumed · **Owner:** repo maintainer

**Notes:** No format rule exists anywhere. Document ids are strictly regex-validated (identifiers.py:21); tag keys are not validated at all. → GAP-027.

**Evidence:**
- `src/docir/modules/tags/application/services/tag_service.py:43-52`
