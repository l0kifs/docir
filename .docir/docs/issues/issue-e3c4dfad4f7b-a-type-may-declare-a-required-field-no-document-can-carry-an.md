---
code:
- src/docir/modules/documents/infra/schema_loader.py
created: '2026-08-06'
description: '''required:'' accepts any name but is checked with getattr on the entity,
  so an unsatisfiable name loads fine and then rejects every add of that type, naming
  the write rather than the schema.'
id: issue-e3c4dfad4f7b
owner: maintainer
related:
- issue-90aea6d1b891
- adr-2a3f625bb2f8
- ref-a6db21f52427
status: resolved
tags:
- material
- schema
title: A type may declare a required field no document can carry, and the schema loads
  anyway
type: issue
updated: '2026-08-06'
---

**Class:** incorrect · **Severity:** material
**Source:** ref-a6db21f52427 re-verification, 2026-08-06 (found while writing issue-90aea6d1b891)
**Step:** authoring `docs-schema.yaml` · **Frequency:** the first time anyone uses `required:`

## Finding

A type may declare `required: [anything]` and the schema loads. Every `add` of that type then
fails, permanently, with no way to satisfy the field.

`_parse_type` checks only that `required` is a list (`schema_loader.py:290-292`) — unlike
`default_status`, transition targets and `inactive_statuses`, which are all checked against the
declared statuses. `Tier0Validator.validate_required_fields` then reads each name with
`getattr(document, name, None)` (`validation.py:33-42`), so a name that is not a `Document`
attribute is `None` for every document ever written.

Reproduced in a throwaway store: a type declaring `required: [code]` rejects every add with
`required field 'code' is missing or empty for type 'probe'`. No CLI flag can supply it, and the
markdown store would drop the key on the next write anyway (`markdown_store.py:118-160`).

## What happens today

The doc comment shipped in every generated schema invites exactly this: "extra frontmatter fields
this type must carry, on top of the always-required id/title/description/type/status/created/
updated" (`default_schema.py:80-81`). It reads as an extension point and is one only for the
handful of names that are already entity attributes (`owner`, `verified`, `tags`, `related`,
`body`, `path`). The failure surfaces at the first write, names a field the author believes they
declared correctly, and does not mention the schema.

## Impact

Same class as the status-name defect the loader already guards: a typo or a wrong assumption in
the schema is reported much later, by a message that points at the write. The schema is the one
file in the store that cannot be rebuilt from the documents, so an author edits it rarely and with
little feedback.

## Proposed default

Validate `required` at load against the set of fields a document can actually carry, and raise
`SchemaError` naming them — the same shape as the existing status check. A schema that cannot be
satisfied should not load.

Deliberately not proposed: making `required` accept arbitrary frontmatter keys. That is a
different feature (arbitrary per-type metadata), it is what issue-90aea6d1b891 needs for `code:`
specifically, and it should be decided there rather than smuggled in as a loosened validation.

## Resolution

FIXED 2026-08-06, as proposed. `_parse_type` now checks every `required:` entry against
`REQUIRABLE_FIELDS` and raises `SchemaError` naming the fields that would have worked — the same
shape as the undeclared-status check beside it, and for the same reason: a schema that cannot be
satisfied should not load.

The allowed set is *derived* from the `Document` dataclass rather than written out, so it cannot
fall behind a new field — `code` landed the same day and needed no edit here. `path` is excluded:
it is a real field, and the file store assigns it *after* Tier 0 runs, so requiring it would
reject every create.

**The fix surfaced its own second half.** With real field names now expressible,
`required: [tags]` was accepted and enforced nothing: `validate_required_fields` treated only
`None` and a blank string as missing, and an empty tuple is neither. A rule that loads, reads as
enforced and enforces nothing is worse than one that is refused — so emptiness now covers
collections, and `required: [tags]` means "at least one tag". `False` stays a value rather than
an absence: `archived: false` is the normal state of a document, and plain falsiness would have
rejected every unarchived one.

Also rewritten: the comment in the shipped `docs-schema.yaml` that described `required` as "extra
frontmatter fields this type must carry". That phrasing is what invited a name no document could
carry; it now says the entry names an existing document field and lists them.

Both halves were confirmed by injecting the bug each claims to catch.

## Actors affected

- ACT-002 repository maintainer / developer

## Evidence

- `src/docir/modules/documents/infra/schema_loader.py:290-292`
- `src/docir/modules/documents/domain/services/validation.py:33-42`
- `src/docir/modules/documents/infra/default_schema.py:80-81`
- `src/docir/platform/filesystem/markdown_store.py:118-160`
