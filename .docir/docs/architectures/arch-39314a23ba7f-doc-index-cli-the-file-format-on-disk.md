---
created: '2026-08-15'
description: 'What a document is as markdown: every frontmatter field, what validates
  it, and the tag registry the tags resolve against.'
id: arch-39314a23ba7f
related:
- kind: refines
  to: arch-1cfb1b212237
status: active
tags:
- architecture
title: Doc-Index CLI — the file format on disk
type: architecture
updated: '2026-08-15'
---

## File format

```yaml
---
id: adr-3f9a2b1c7d4e            # `random` id_style; `sequential` mints adr-0007
title: Auth strategy
description: How the service authenticates API clients and refreshes tokens.
type: decision
status: accepted
tags: [auth, api]
related:                          # typed edges: bare id = relates_to
  - adr-0003
  - to: adr-0001
    kind: supersedes
created: 2026-06-15
updated: 2026-06-30
owner: platform-team             # optional: staleness steward
verified: 2026-06-30             # optional: last human re-confirmation
code:                            # optional: the code this document governs
  - src/auth/**
  - tests/test_auth.py
---
```
Body: standard markdown, human-readable, diffs cleanly in git.

## Frontmatter fields

| Field | Required | Set by | Description |
|---|---|---|---|
| `id` | yes | `docir add` (auto-generated) | `<type-prefix>-<suffix>`, never chosen manually. The suffix depends on the type's `id_style`: `random` (`adr-3f9a2b1c7d4e`) is what `docir init` writes by default, because two branches of one repo each have their own index and would otherwise both mint `adr-0007`; `sequential` (`adr-0007`) is opt-in via `docir init --id-style sequential` for readable numbers within a single store. `--id` adopts an existing id, for migrating a corpus whose numbers are already cited |
| `title` | yes | `docir add`, `docir update --set-title` | Canonical document title. Frontmatter-only source of truth; the CLI never enforces or generates a body heading from it |
| `description` | yes | `docir add`, `docir update --set-description` | One- or two-sentence summary of the document, written by the agent at creation and kept current on meaningful edits. Feeds search quality — indexed in FTS and included in the embedded text — and shown in `docir query`/`docir context` result listings so the agent can judge relevance without fetching the full body |
| `type` | yes | `docir add` (fixed at creation) | Document type (`decision`, `issue`, `architecture`, ...); selects the grammar that applies. That grammar is **not** only `docs-schema.yaml`: the frozen core and the named profiles are merged in from the installed package on every command, so an upgrade can change a type's rules with nothing in `git diff` — see "Schema drift and the index build stamp" |
| `status` | yes | `docir add` (default), `docir update --status` | Type-specific enum (e.g. `decision`: proposed/accepted/rejected/superseded; `issue`: open/resolved). Transitions are validated against `docs-schema.yaml` |
| `tags` | no | `docir add --tags`, `docir update --set-tags` | List of tag keys for `docir query --tag` filtering. Each key must exist in the tag registry (Tier 0 validation) — free-form tags are rejected, preventing synonym sprawl |
| `related` | no | `docir add --related`, `docir update` | List of **typed edges** to other documents (`<id>` = default `relates_to`, or `{to, kind}`); forms the relation graph used for traversal and Tier 1 graph checks. Kinds come from the schema's `relation_types` registry (unknown kind = Tier 0 error); a type may whitelist kinds/targets via `allowed_relations` |
| `created` | yes | `docir add` (auto) | Set once, never modified afterward; used for audit/sort queries |
| `updated` | yes | `docir add` / `update` / `archive` / `unarchive` | Stamped whenever one of those calls actually changes something. Deliberately **not** advanced by the mechanical rewrites — `check --fix`, the unlinking half of `delete --force`, and `tag rename` / `tag rm --force` — because staleness falls back to `updated` when there is no `verified`, so a mechanical bump would launder the review clock. `TagService` has no `Clock` for exactly this reason |
| `owner` | no | `docir add --owner`, `docir update --set-owner` | Optional steward, surfaced by the staleness check; written only when set |
| `verified` | no | `docir update --verified` | Optional date a human last re-confirmed the doc is still correct; resets the staleness clock (staleness measures from `verified`, else `updated`) |
| `code` | no | `docir add --code`, `docir update --set-code` | Repo-relative globs naming the code this document governs, so a later session can ask `docir query --code <path>` which decisions concern the files it is about to change. Only the *shape* is validated on write — absolute paths, `..` segments, backslash separators and empty entries are refused, but a pattern matching nothing today is accepted, because a decision is routinely written before the code it decides. `docir check` reports `unmatched-code` once a pattern stops matching, and only when the store sits in a repository. The index returns them sorted; the file keeps the author's order |
| `archived` | no | `docir archive` / `docir unarchive` | Absent by default; `true` removes the document from active search (FTS, embeddings) while keeping the file and index rows |

`created` is set once by `docir add` and never modified afterward. `updated`
is refreshed by the CLI on every `docir update` call (metadata or body). The
distinction matters for Tier 1 checks (e.g. a recently created orphan doc
vs. a long-standing one are different signals) and for audit queries like
"decisions made last quarter", which should sort on `created` rather than
`updated`.

`title` is stored only in frontmatter — it is the canonical source used by
the index for listings, `docir query`, and `docir context` results. The CLI
does not enforce or auto-generate any heading in the body; the agent
decides what (if anything) to write there, including whether to repeat the
title as an `# H1`.

`archived` is an optional frontmatter field, absent by default and set to
`true` only by `docir archive` (removed again by `docir unarchive`) — see
"Archiving vs. deletion" below.

## Tag registry

Tags are not free-form strings — they are registered entities, each with a
unique key and a description. The registry is the source of truth for what
tags exist, versioned in git like everything else (a `docs/tags.yaml`
mapping key → description; promotable to a full tag doc-type later if tags
need their own relations/history).

```yaml

# docs/tags.yaml
auth:    "Authentication, authorization, tokens, sessions."
api:     "Public/internal HTTP API surface and versioning."
storage: "Persistence, database schema, migrations."
```

- **Referential integrity (Tier 0):** every key in a document's `tags`
  must exist in the registry. An unknown tag is a hard error at
  `docir add`/`docir update` time — "unknown tag, register it first" — the
  same guarantee applied to `related` ids. This eliminates the main
  failure mode of free-form tags: synonym sprawl (`auth`,
  `authentication`, `Auth`) fragmenting the same concept.
- **Descriptions feed search:** a tag's description is available to
  `docir context` so the agent (and the semantic layer) can reason about
  what a tag means, not just match the bare key.
- **CLI:** `docir tag add <key> --description "..."`, `docir tag list`,
  `docir tag rename <old> <new>` (rewrites the key across all referencing
  documents), `docir tag rm <key>` (blocked while any document still uses
  it, unless `--force`). Unlike a dangling `related` id, a `--force` tag
  removal does not leave broken keys behind: since a tag is a classifier
  rather than a link, the CLI strips the removed key from the `tags` list
  of every referencing document (rewriting those files and reindexing
  them) as part of the same operation.
