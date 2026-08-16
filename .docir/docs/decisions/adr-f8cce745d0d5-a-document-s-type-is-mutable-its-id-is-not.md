---
code:
- src/docir/modules/documents/infra/schema_loader.py
- src/docir/modules/documents/application/services/document_service.py
- src/docir/platform/filesystem/markdown_store.py
created: '2026-08-15'
description: Why docir update can retype a document while its id and prefix stay put,
  and why a schema can subtract a type the core or a profile contributed.
id: adr-f8cce745d0d5
owner: maintainer
related:
- issue-4952ce77d19d
- issue-ab138501abfd
- kind: refines
  to: adr-2a3f625bb2f8
- kind: refines
  to: arch-1cfb1b212237
status: accepted
tags:
- schema
- cli
title: A document's type is mutable; its id is not
type: decision
updated: '2026-08-15'
---

## Context

A corpus outgrows the vocabulary it started with. A store on the bundled
`software` profile ends up calling a decision something else, and renaming the
type means two things docir could not do: change a document's `type`, and stop
the schema from declaring the old name.

Neither was an oversight so much as an untested direction. Schema resolution
only ever added types, and the write path patched every frontmatter field except
the one that selects the grammar for the rest.

## Decision

**A document's type is mutable; its id is not.** `docir update <id> --type`
retypes one document. The id is left exactly as it is, including its prefix: it
is the corpus's only address, written into every `related` edge that points at
the document and into every reference outside the store. A prefix therefore
records which type *minted* an id, never which type owns it now — the same
reading `docir add --id` already relies on when it adopts a numbered corpus.

**The schema can subtract.** `disable_types: [decision]` removes a type the core
or a profile contributed, which is also what frees its prefix for another type
to claim. Nothing else could: the core is merged whenever a `profiles:` key is
present, and an inline block can only override a type by its own name.

## The rules that make a retype safe

**Status is checked for membership, not transition.** A retype is not a status
change, so the old type's transition graph says nothing about the new type's.
The current status is kept if the new type declares it, and otherwise the write
is refused, naming the statuses that would work. It is not quietly reset to the
new type's `default_status`: doing that across a corpus rewrites every
`accepted` to `draft` and reports success.

**The edges are re-checked against the new type.** `allowed_relations` is a
property of the source type, so a retype can move a document under a whitelist
its existing edges do not satisfy. They are validated even when the call does
not touch them, because this write is what would persist them.

**The file moves; the filename does not.** The path encodes the type as its
directory, so the file is written under the new one and the old is dropped. The
filename carries over untouched — a retype is not a retitle, and reslugging
would hide the move inside a rename git cannot follow.

**Retyping works *out of* a type the schema no longer declares.** This is what
makes the pair usable at all. Declaring the replacement type first is impossible
while the old one holds the prefix, and disabling the old one first leaves the
corpus on an unknown type — so if a retype required a known source type, the two
halves would deadlock and the only way through would be the hand-editing both
exist to remove. Status, edges and required fields are all validated against the
*target* type, which is the one the document is about to have.

## Consequences

- Renaming a corpus's vocabulary is a schema edit plus a loop over
  `docir query --type <old>`, with every write validated. There is still no bulk
  retype verb, for the reason there is no bulk import: it would have to guess
  the status mapping.
- A store can now hold documents whose id prefix matches no type. That is
  intended and needs no repair; `docir check` says nothing about it.
- Disabling a type documents still use leaves them `unknown-type` in
  `docir check`, next to the `schema-drift` finding that names the cause. That
  was already true of disabling a profile.
- The frozen core still stands and is still merged unconditionally
  (adr-2a3f625bb2f8). `disable_types` subtracts *after* the merge, so profile
  precedence is untouched — what changes is only that "always merged" stops
  meaning "always present".
