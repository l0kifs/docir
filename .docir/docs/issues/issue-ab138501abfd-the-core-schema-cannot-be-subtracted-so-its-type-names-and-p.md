---
code:
- src/docir/modules/documents/infra/schema_loader.py
- src/docir/modules/documents/infra/profiles.py
created: '2026-08-15'
description: 'Every profiles: key merges the core unconditionally, so decision and
  its adr prefix exist in every store — an unused name stays addable and its prefix
  cannot be reused.'
id: issue-ab138501abfd
owner: maintainer
related: []
status: resolved
tags:
- schema
- blocking
title: The core schema cannot be subtracted, so its type names and prefixes are claimed
  forever
type: issue
updated: '2026-08-15'
---

Schema resolution is additive. `_merge_profiled` prepends `CORE_SCHEMA_YAML`
whenever the file carries a `profiles:` key — `profiles: []` included — and an
inline `types:` block can only override a type *by its own name*. Nothing
removes one.

## A prefix is claimed forever

The core `decision` declares `prefix: adr`, and `Schema.__post_init__` refuses
two types sharing a prefix. A store renaming its decisions to
`product_decision` while keeping its `adr-...` ids — the ids are the corpus's
only addresses, so they must survive a rename — cannot declare that type at
all: `prefix 'adr' used by both 'decision' and 'product_decision'`.

## An unused name stays addable

A store that never uses `decision` still accepts a write of that type. The name
resolves, the write validates, the document lands in a namespace the corpus does
not use, and nothing reports it. Two names for one concept is the split docir
exists to prevent, shipped in the default schema.

## Why the file cannot say so

The comment in the generated `docs-schema.yaml` explains the merge but reads as
advice; the core is not one of the profiles the file lists, so removing every
profile does not remove it. Anyone who works that out from the error message has
already tried `profiles: []` and been told the same thing twice.
