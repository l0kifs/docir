---
created: '2026-08-16'
description: 'How a corpus renames a type and keeps the ids it already has: disable_types
  frees the prefix, then documents are retyped one at a time.'
id: run-781485012ad0
owner: maintainer
related:
- adr-f8cce745d0d5
status: active
tags:
- schema
- cli
title: Rename a document type
type: runbook
updated: '2026-08-16'
---

Merging only adds. The core, the enabled profiles and any inline `types:` are
unioned, so nothing written in `docs-schema.yaml` can remove a type the core or a
profile already declares. `disable_types:` is how a schema subtracts — and the
reason to reach for it is rarely the name.

## The prefix is what you are really after

A schema refuses two types that share a `prefix`, so while the core's `decision`
resolves, no other type can claim `adr`. A corpus that has been minting `adr-...`
ids for a year and now wants its own name for that concept needs exactly that
prefix freed: the ids are already written into every `related` edge, and
re-minting them is not on the table.

The second half is smaller but real. Leaving the unused name addable ships two
names for one concept in the default schema — the duplication docir exists to
prevent.

## Edit the schema

```yaml
# docs-schema.yaml
profiles: [software]
disable_types: [decision]        # the name stops resolving, and `adr` is free
types:
  product_decision:
    prefix: adr                  # the corpus keeps every adr-... id it has
    default_status: draft
    statuses: {draft: [active], active: []}
```

Two rules are checked when the file loads, both reported naming what would have
worked: the disabled name must be in the resolved set — a typo that silently does
nothing forever is the failure mode — and it may not be a name the same file also
declares inline, a contradiction with no reading worth guessing.

## Check the edit before it reaches a write

```bash
docir schema validate
```

It answers two things: whether the file loads, and what the edit costs the corpus —
how many documents carry a type, status, required field or relation kind this
schema no longer accepts.

It reads the files rather than the index, so it works on a fresh clone, and it
never changes the exit code. The schema is valid; the documents are what moved.

## Retype the documents

Nothing is retyped for you, because only you know what each old status becomes.

```bash
docir query --type decision --limit 500 | jq -r '.[].id' \
  | xargs -I{} docir update {} --type product_decision --status active
docir reindex && docir check
```

The status is validated for **membership in the target type**, not as a
transition — the type being left has no transition graph reaching a different
type's. A status the new type does not declare is refused rather than reset,
because falling back to the default would rewrite every `accepted` in the corpus
to `draft` and report success.

The existing `related` edges are re-validated against the new type even when the
call does not supply them: `allowed_relations` belongs to the source type, and
this write persists them.

## What check reports in between

Between the schema edit and the loop, the not-yet-moved documents are reported as
`unknown-type` — a warning, so nothing is blocked and no build goes red. Beside it
`schema-drift` names the cause.

That intermediate state is what a correct migration passes through, which is why
neither finding is an error.

## The id never changes

Retyping never re-mints an id, prefix included. `adr-3f9a2b1c7d4e` stays itself
under any type, because it is the only address every `related` edge has for it. A
prefix records which type *minted* an id, never which type owns it now.

The file moves to the new type's directory keeping its filename — a retype is not
a retitle — and the vacated directory is pruned, because listing the docs folder is
how a person reads which types a store uses. It is not a content change, so nothing
is queued for re-embedding.
