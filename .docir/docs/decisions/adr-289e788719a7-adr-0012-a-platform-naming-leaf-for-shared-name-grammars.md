---
created: '2026-07-30'
description: Why the tag-key grammar lives in platform rather than being written twice
  or crossing a module boundary.
id: adr-289e788719a7
owner: maintainer
related:
- kind: refines
  to: arch-322e5f992ad2
status: accepted
tags:
- architecture
- tags
title: 'ADR-0012: A platform.naming leaf for shared name grammars'
type: decision
updated: '2026-07-30'
---

# ADR-0012: A `platform.naming` leaf for shared name grammars

Status: accepted
Date: 2026-07-30

## Context
GAP-027 asked for a format rule on tag keys: any non-empty string was accepted,
so `auth`, `Auth` and `authentication` could all exist and nothing objected.
The agreed shape (option 1 of three) was to **reject** a non-conforming key on
the write paths that mint one, and **warn** about keys already in a store — no
silent normalisation, because lowercasing somebody's key rewrites their data.

That splits the rule across two modules:

- `tags` applies it on `tag add` / `tag rename` (Tier 0, a hard rejection).
- `documents` applies it in `docir check`, whose `GraphChecker` already receives
  the registry as data (`known_tags`) and now reports `tag-key-format`.

Neither module may import the other. The dependency graph allows only
`tags -> documents -> indexing`, so a `documents -> tags` import would close a
cycle, and `tach` fails the build on it. The alternatives were:

1. Write the regex twice. Two definitions of one grammar, guaranteed to drift —
   and the entire point of a controlled vocabulary is that there is one rule.
2. Have `tags` produce the `CheckIssue` and let the dispatcher merge two result
   lists. This needs a new `tags -> documents.api` edge for the `CheckIssue`
   type, and puts the decision of what counts as a finding into the wiring
   layer, which is meant to hold no business logic.
3. Move the shared thing into `platform` — one of the three sanctioned responses
   to a boundary error, alongside "route through the module's api" and "merge
   the modules".

## Decision
Add `docir.platform.naming`, a pure leaf (`depends_on = []`) holding name
*grammars* — rules about the shape of a key, not its meaning. It currently
exports `TAG_KEY_PATTERN`, `TAG_KEY_RE`, `TAG_KEY_RULE` (the human-readable
form, so the error message and the check finding cannot describe different
rules) and `is_valid_tag_key`.

`tags.application` and `documents.domain` both depend on it. Both edges point
the sanctioned direction (`module -> platform`); no cross-module edge is
created and the deprecated baseline is untouched.

The module is pure — no I/O, no framework — which is what makes it importable
from a `domain` layer at all, the same property that lets `platform.errors` and
the `Embedding` value object be imported there.

## Consequences
- One grammar, named once. The rejection message and the `check` finding quote
  the same `TAG_KEY_RULE` string.
- `platform` grows a fifth pure capability. This is the ADR the architecture
  rules require for a platform addition (§14).
- Validation is a **write-path** concern only. `is_valid_tag_key` must never be
  called to reject on a read: a store written before the rule can hold keys that
  fail it, and refusing to load them would make an old corpus unreadable rather
  than merely untidy. `tag rename` therefore validates the new key and not the
  old one — renaming away from a legacy key is the migration path, and
  validating `old` would trap exactly the keys the rule wants gone.
- `tag-key-format` is a **warning** and must stay one. `tag add` rejects bad keys
  now, so the only way to hold one is to predate the rule; failing a `--strict`
  build for that would repeat GAP-006, where a gate that fired on a healthy
  corpus got switched off and took duplicate-id detection with it. `check --fix`
  does not repair it either: the fix is a rename, and only a human knows whether
  `Auth` meant `auth` or `authn`.
- Scoped out: the document-id grammar stays in
  `documents.domain.value_objects.identifiers`. It is used by one module, so it
  has no reason to move; if a second module ever needs it, this is where it goes.
