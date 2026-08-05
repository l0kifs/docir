---
created: '2026-07-30'
description: 13 terms defined with owner and evidence, including the words that mean
  two things.
id: ref-cbf147832c37
owner: maintainer
related:
- arch-1cfb1b212237
- adr-20eec6e2e2ca
- adr-bd7c4f3c5764
- issue-40d1792bc9f9
- issue-8c37bf22ba3c
- issue-8d5b5b45e2fc
- issue-93152f7b9213
- issue-9cb85759076d
- issue-a40dbcc7a19a
- issue-b4f441c7210f
- issue-b7ddde3ce860
- issue-d8295c5c76d1
- issue-efc29234eb57
status: active
tags:
- docs
title: Glossary — one term, one definition, one owner
type: reference
updated: '2026-08-05'
---

Synonyms and homonyms are findings, not tidy-ups: where one word means two things
(`stale`, `resolved`), that is recorded rather than smoothed over.

## document

One markdown file with YAML frontmatter, identified by a type-prefixed id, and the unit of everything docir does: validation, retrieval, relation, staleness.

**Owner:** repo maintainer · **Used in:** documents, indexing, tags, CLI

**Evidence:**
- `src/docir/modules/documents/domain/entities/document.py:19-38`

## index

The derived SQLite projection of the documents — metadata, FTS5 full text, relation graph, embedding vectors and the id counter. Gitignored and rebuildable.

**Owner:** repo maintainer · **Used in:** platform.persistence, documents, indexing

**Conflicts:** 
- *context* the "rebuildable" claim; *definition* "Rebuildable" is true of six of the seven tables. `id_sequences` is part of the index by every structural definition (it lives in the index database, is created by the index migration, is gitignored) but is NOT reconstructed by `reindex`. The word "derived" is doing work it cannot support for that one table, and the consequence is issue-b7ddde3ce860.; *gap* issue-b7ddde3ce860

**Evidence:**
- `README.md:20-35`
- `src/docir/platform/persistence/alembic/versions/0001_initial_index.py`

## stale

OVERLOADED — three unrelated meanings in one codebase: (1) a document past its type's review cadence (the product feature, adr-bd7c4f3c5764); (2) an index row whose file changed out-of-band (`StaleWriteError`, the concurrency guard); (3) an index row for a file that no longer exists (`for stale in uow.documents.all()` in the reindex removal sweep).

**Owner:** repo maintainer · **Used in:** documents.domain, documents.application, platform.errors

**Conflicts:** 
- *context* document_service.update(); *definition* The local variable `stale` (sense 2) sits eleven lines from `self._is_stale(...)` (sense 1) in the same method. Both are booleans about the same document and they mean entirely different things.; *gap* issue-d8295c5c76d1

**Evidence:**
- `src/docir/modules/documents/domain/services/graph_checks.py:84`
- `src/docir/platform/errors/__init__.py:101-104`
- `src/docir/modules/documents/application/services/document_service.py:136`
- `src/docir/modules/documents/application/services/maintenance_service.py:168`

## archived

A document withdrawn from retrieval but kept on disk and in the metadata table. Set by `docir archive`; reversible.

**Owner:** repo maintainer · **Used in:** documents, indexing

**Conflicts:** 
- *context* inactive status; *definition* `inactive_statuses` (e.g. `resolved`, `superseded`, `deprecated`) also withdraws a document from the list read paths. Two independent mechanisms with near-identical user-visible effect, different flags to defeat (`--include-archived` vs `--include-resolved`), and different enforcement points — which is why one of them leaks through graph expansion and the other does not.; *gap* issue-8c37bf22ba3c

**Evidence:**
- `src/docir/modules/documents/application/services/document_service.py:161-188`

## resolved

In the CLI: the flag name `--include-resolved` for "also show documents in an inactive status" — on every type, including ones with no status called `resolved`.

**Owner:** repo maintainer · **Used in:** CLI, documents.application

**Conflicts:** 
- *context* the schema; *definition* `resolved` is a status of exactly two types (`issue` in the software profile, `incident` in ops). For a `decision` the flag means "include rejected and superseded"; for a `policy`, "include superseded and retired". The wire field is named `include_inactive` — correctly — and the CLI renames it to something narrower on the way out. A user asking for decisions cannot guess that `--include-resolved` is the flag they need.; *gap* issue-efc29234eb57

**Evidence:**
- `src/docir/entry_points/cli/app.py:269`
- `288`
- `303`
- `src/docir/entry_points/dispatch.py:116`

## related

The outgoing typed edges of a document (`RelatedRef{target, kind}`).

**Owner:** repo maintainer · **Used in:** documents.domain, platform.persistence, frontmatter

**Conflicts:** 
- *context* on disk vs in the API; *definition* In frontmatter an entry is either a bare id or `{to: <id>, kind: <k>}`. In JSON output the same edge is `{target: <id>, kind: <k>}`. The key is `to` in one representation and `target` in the other, for the same field of the same object.; *gap* issue-8d5b5b45e2fc

**Evidence:**
- `src/docir/modules/documents/domain/value_objects/relations.py`

## level

A per-type integer expressing architectural abstraction height; a dependency edge from a higher level to a lower one is reported as a layering violation.

**Owner:** repo maintainer · **Used in:** documents.domain.schema, graph_checks

**Conflicts:** 
- *context* the shipped software profile; *definition* The levels assigned (decision 3, issue 1) make the ordinary and intended relationship "this decision addresses that issue" a violation. The term's definition and the shipped values disagree about what the ordering means.; *gap* issue-40d1792bc9f9

**Evidence:**
- `src/docir/modules/documents/domain/schema.py:46-47`
- `src/docir/modules/documents/domain/services/graph_checks.py:194-223`

## check / lint

`check` = Tier 1, structural, non-blocking-but-CI-gateable. `lint --deep` = Tier 2, advisory heuristics.

**Owner:** repo maintainer · **Used in:** CLI, documents.application

**Conflicts:** 
- *context* `--strict`; *definition* `check` is documented as producing "warnings rather than failing an agent mid-task" (graph_checks.py:3-5), yet `--strict` turns every one of them into a build failure with no severity distinction. The tier model says these are warnings; the CI integration treats them as errors.; *gap* issue-9cb85759076d

**Evidence:**
- `src/docir/entry_points/cli/app.py:419-456`
- `CLAUDE.md`

## score

The reciprocal-rank-fusion value for a context result.

**Owner:** repo maintainer · **Used in:** indexing.domain, CLI output, README

**Conflicts:** 
- *context* what a reader will assume; *definition* Published as a bare number in agent-facing JSON, where it reads as a relevance measure. It is a rank-position artefact: bounded near 1/(k+1)+1/(k+1) ≈ 0.033, essentially identical for a perfect match and a nonsense query. README:95 says "ordering is the point", which is correct — but the value is still emitted, and nothing prevents an agent thresholding on it.; *gap* issue-93152f7b9213

**Evidence:**
- `src/docir/modules/indexing/domain/scoring.py:44-73`
- `README.md:90-95`

## home / store

The single resolved directory holding docs/, docs-schema.yaml and the index.

**Owner:** repo maintainer · **Used in:** config, CLI, docs

**Conflicts:** 
- *context* naming; *definition* Called "home" in code and `--home`/`DOCIR_HOME`, "store" in the CLI help and adr-20eec6e2e2ca, and "data root" in the `--home` option help — three names for one concept in user-facing text.; *gap* issue-a40dbcc7a19a

**Evidence:**
- `src/docir/config/settings.py:51-104`

## profile

A named bundle of document types layered onto the frozen core schema.

**Owner:** repo maintainer · **Used in:** documents.infra, CLI

**Evidence:**
- `src/docir/modules/documents/infra/profiles.py:41-208`

## skeleton

A `DocumentSummary`: frontmatter, typed edges and staleness, with no body. The unit the list read paths return and the source of the token savings.

**Owner:** repo maintainer · **Used in:** documents.application, README

**Evidence:**
- `src/docir/modules/documents/application/dto.py:84-108`

## owner

A free-form string naming who is accountable for re-verifying a document.

**Owner:** repo maintainer · **Used in:** documents.domain, graph_checks

**Conflicts:** 
- *context* what the word implies vs what it does; *definition* The word implies an accountable party. The field is written, stored, and interpolated into one `check` message — nothing else. It cannot be queried or filtered on, triggers no notification, and is not validated against anything. It names a responsibility the system never routes to anyone.; *gap* issue-b4f441c7210f

**Evidence:**
- `src/docir/modules/documents/domain/entities/document.py:37`
