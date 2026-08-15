---
created: '2026-08-15'
description: 'What happens when a document is created, edited, archived or deleted:
  id allocation, schema validation, the index update, and how a diverged file is handled.'
id: arch-0368cc754c15
related:
- kind: refines
  to: arch-1cfb1b212237
status: active
tags:
- architecture
title: Doc-Index CLI — the write path
type: architecture
updated: '2026-08-15'
---

## Write path

Agent → `docir update` / `docir add` → CLI validates schema → writes to the
.md file → CLI updates that single file's index rows (metadata, FTS5,
relations) synchronously in the same command call, and schedules the
embedding recompute asynchronously (see Semantic layer). Everything except
the embedding is current the moment the command returns; the embedding
follows within seconds.

## Document creation (`docir add`)

```
docs add --type decision --title "Refresh token rotation" \
  --description "When and how refresh tokens are rotated on renewal." \
  --tags auth,api --related adr-0007 \
  --body-file draft.md
```

Steps performed by the CLI:

1. Generate `id` from the type's prefix and its `id_style`. A `random` type mints a
   collision-resistant suffix and retries if the index already holds it; a `sequential`
   type draws the next number from the database counter (`id_sequences`) in **one**
   atomic upsert — not by scanning files, and not by a read-modify-write in Python,
   which let concurrent `--no-daemon` processes all read the same value.
2. Assemble frontmatter from arguments plus type defaults (e.g.
   `status: proposed` for `decision`, `status: open` for `issue`) and
   auto-set `created` and `updated` to today.
3. Validate: required fields per type (including `title` and
   `description`, which the agent must supply at creation), `status` must
   be a valid enum value for that type, every id in `related` must already
   exist in the index.
4. Accept the body via `--body-file`, `--body "text"` for short content,
   or `--stdin` — the most agent-friendly option, avoiding shell-escaping
   issues with multi-line markdown.
5. Write the physical file to `docs/<type>s/<id>-<slug>.md`.
6. Synchronously index it: `INSERT` into `docs`, `relations`, and FTS5,
   and flag the row for embedding (computed asynchronously — see Semantic
   layer).
7. Return the generated `id` and file path to the caller, so the agent can
   reference the new document later in the same session.

## Document editing (`docir update`)

Two distinct operations, kept separate rather than merged into one:

- **Metadata update** (frequent, low-risk):
  `docir update issue-12 --status resolved` — patches only specific
  frontmatter fields, body untouched. `--set-title "..."` /
  `--set-description "..."` update those fields the same way.
- **Body update** (higher-risk) — three supported modes:
  - `--append-section "Resolution" --body "Fixed in PR #42"` — appends a
    new heading/section at the end without touching existing content.
    **Default, safest path** — fits patterns like "issue closed → note how".
  - `--replace-section "<heading>" --body "..."` — replaces content under
    a specific existing heading.
  - `--replace-body --force` — full body replacement. Requires an explicit
    force flag because it can silently overwrite content the agent never
    read in full; agents should `docir get` first.

When a body edit changes what the document is fundamentally about, the
agent is expected to update `description` in the same call (e.g.
`--append-section ... --set-description "..."`), keeping the summary
that drives search in step with the content — the same discipline applied
to `title`.

## Write conflict handling

`update` compares the `content_hash` the index holds against the file's and calls
the result `disk_diverged`. It is consulted in **one** branch, and that scoping is
the rule rather than an oversight.

Every edit is applied to the document *as it is on disk*: the command re-reads the
file, then stages the change onto that. So `--append-section`, `--replace-section`
and any metadata patch **compose** with an out-of-band change and cannot destroy
it — there is no merge algorithm to get wrong, because there is nothing to merge.
`--replace-body` is the only mode that discards the on-disk body, so it is the
only one where divergence means data loss, and the only one that refuses:

```
docir update <id> --replace-body --force --body "..."
  -> error: <id> changed on disk since it was indexed; refetch with docir get <id>
```

It also requires `--force` independently, because overwriting a whole body is worth
one deliberate keystroke even when nothing diverged.

Extending the guard to the other modes would fail writes that lose nothing —
`--set-title` refusing because someone fixed a typo by hand. `TestDiskDivergenceScoping`
pins that.

**It is a divergence check, not optimistic concurrency control.** No caller supplies
a version token, so it cannot see a competing *writer*, only a file that changed
since it was indexed. The daemon serializes requests, which is what makes that
adequate in practice; `docir --no-daemon` parallel writers have a small unguarded
window.

The variable is `disk_diverged`, not `stale`. In this codebase `stale` means a
document past its review cadence — a different concept on a different clock.

## Per-type schema

Required fields, valid status enums, and allowed status transitions (e.g.
`open → resolved`, not the reverse without an explicit override) are
defined in a `docs-schema.yaml` config, not hardcoded in the CLI — new
document types can be added without changing CLI code. A type also declares its
`review_days` staleness cadence and, optionally, `allowed_relations`
(`{kind: [target types]}`) constraining which typed edges it may declare. The
valid relation kinds are a top-level `relation_types` registry (permissive when
absent, for schemas predating typed edges).

**Core + profiles.** The schema is composed, not monolithic: a frozen
domain-agnostic **core** (the `decision` type, the relation registry, cadences)
plus named **profiles** that layer domain types — `software`
(issue/architecture/release_note), `research`, `ops`, `qa` (test_plan/test_case),
`legal`. A `docs-schema.yaml` selects them with `profiles: [..]`; the loader
merges `core → profiles → the file's inline overrides`. The default is
`profiles: [software]`. This keeps generalizing docir to a new domain a matter of
picking a profile rather than mutating the base schema. Because the merged result
— not the file — is what validation enforces, `docir schema show` prints it and
`docir schema validate` checks an edit; both run in-process, since a schema too
broken to build the container is exactly when they are needed. See
adr-599055502f0e/0006/0007/0010 for typed edges, staleness, profiles, and schema
introspection respectively.

## Index consistency

The index update is not tied to git at all — it happens synchronously inside
`docir update` / `docir add`, as part of the same operation (the embedding is the
one deferred piece — see the semantic sections above — but metadata, FTS5 and
relations are immediate). Git commits are just a snapshotting mechanism on top of
files that are already consistent with the index.

`docir reindex [--changed]` rebuilds the index from the canonical files. It is no
longer only a manual fallback: the daemon watches `docs/` and runs it on what
changes, so a hand-edited file is picked up without anyone remembering to. Run it
by hand after a merge, a pull or a fresh clone — the index is gitignored, so a
clone has none — and to recover from corruption.

Three things about it are load-bearing:

- **`--changed` is not a different result, only less work.** It skips re-saving
  files whose content is unchanged. The removal sweep runs in **both** modes: it
  used to be skipped under `--changed`, which gave the fast path quietly
  different semantics — a document deleted from the filesystem stayed in the
  index and kept being returned by every read path.
- **Read `documents_skipped`.** A source file whose frontmatter will not parse is
  skipped, not indexed: it exists on disk and is invisible to every read path. A
  rebuild that quietly dropped a document used to look exactly like one that did
  not. Non-zero means run `docir check`, which names each file.
- **It restores derived state the files do not carry.** The id counter is raised
  to the highest suffix on disk, and the schema baseline and the version stamp
  are rewritten — `reindex` is the only writer of all three, because it is the
  verb that already means "make the derived state agree with the sources".

## Archiving vs. deletion

Two distinct operations with different reversibility, since an archive-only policy
would let the archive grow unbounded forever:

- **`docir archive <id>`** — soft, reversible. Sets `archived: true` in the
  document's own frontmatter (the file is the source of truth, same as `status`)
  and removes it from active search surfaces (FTS5, embeddings) in the index.
  `docir unarchive <id>` removes the field again. Because the flag lives in the
  file itself, a full `docir reindex` from a fresh clone correctly keeps archived
  documents out of active search without any side-channel state.
- **`docir delete <id>`** — hard, irreversible within the tool itself. Deletes the
  physical file and all its rows (metadata, FTS, embeddings, chunks, relations).
  Since git still holds the file's history this is not true data loss — consistent
  with "git is the source of truth, the index is derived". Used sparingly.

**Referential integrity on delete.** If other documents link to the id, `docir
delete` fails by default (Tier 0 style) rather than silently leaving a dangling
reference, and names the referrers.

`--force` deletes anyway, and **compensates for the edges it breaks**: it strips
the edge from every referencing document in the same transaction and returns their
ids, which the CLI prints as "unlinked from ...". So a forced delete cannot leave a
dangling reference — the pattern `tag rm --force` already used for tags.

That is not a nicety. `dangling` is an **error**-severity Tier 1 finding, not a
warning: it means the corpus is broken and `docir check --strict` fails on it. And
because Tier 0 only validates the edges supplied in the *current* call, a
referencing document left holding a dead id would re-persist it to the canonical
file on its next unrelated `update`. Detect-only was a state the product could
notice and not exit.

The compensating write deliberately does **not** advance the referrers' `updated`.
It follows `check --fix`, not a human edit: staleness records when someone last
vouched for the content, and having a link removed from underneath you is not
that.

One consequence for the test suite: `delete --force` can no longer manufacture a
dangling edge, so the fixture that needs one builds it the way it really arises —
remove the target's file as a merge would, then `docir reindex`.
