---
code:
- src/docir/platform/naming/__init__.py
- src/docir/modules/documents/domain/entities/document.py
- src/docir/platform/persistence/repositories.py
- src/docir/modules/documents/domain/services/graph_checks.py
created: '2026-08-17'
description: Why ids named in a body become mention edges, why only the orphan check
  reads them, and why they are not in frontmatter.
id: adr-e86c5040d626
owner: maintainer
related:
- adr-289e788719a7
- adr-599055502f0e
- arch-ad342aae8293
status: accepted
tags:
- architecture
- cli
- persistence
title: A second relation graph, derived from the prose
type: decision
updated: '2026-08-17'
---

`docir check` reported `orphan` for every document whose author had linked it by writing its
id in a sentence — which is how most people link. The finding claimed "nothing connects to
this" and measured only whether somebody had edited `related:` frontmatter.

That mattered beyond the noise. `orphan` firing on a healthy corpus is half the reason the
`--strict` gate had to stop failing on warnings, which is the machinery that also carries
duplicate-id detection.

## The decision

A second, derived relation graph. `Document.mentioned_ids(prefixes)` scans a body for
document ids; the result is stored in a `mentions` table, rebuilt by `docir reindex`, and
never written back to frontmatter. `related:` stays the authored, typed layer.

`orphan` reads both. Nothing else does.

## Why only orphan reads it

Every other check that touches the graph would be wrong to see inferred edges. `cycle` would
report mutual citation, which is how prose works. `dangling` is an *error* that gates a merge,
and a body naming an id that does not resolve is ordinary — an ADR routinely references the
issue it will produce. `layering` reads edges the schema marks as dependencies, and a mention
asserts no direction at all. The delete guard would refuse to remove a document because
somebody quoted its id in a paragraph.

So the derived edges live in their own table rather than in `relations`. Sharing the table
would have made every one of those checks opt *out*, and the one that got forgotten would fail
in the direction that blocks work.

## What resolution means

`mentions.target` carries no foreign key, and reads join against the indexed documents. A
mention of an id no document holds is stored and simply not returned.

This is what lets a forward reference work. An ADR naming the issue it will produce has to
start resolving when that issue is written — not when somebody remembers to re-save the ADR.
Storing only resolvable mentions would have made the graph depend on the order documents were
created in.

A document naming its own id is describing itself, not linking to itself, and is excluded by
the entity, which is the only place that knows the id.

## Where the grammar lives

In `platform.naming`, beside the tag-key rule and for the same reason (adr-289e788719a7):
`DocId` mints exactly what the scanner has to recognise, and two copies of that pattern would
let a document be addressable by one reader and invisible to the other. `DocId` now uses it
rather than carrying its own.

The scan is restricted to the prefixes the schema declares. Left open, any hyphenated word
with a hex tail is an id, and `sha-1beef` in a sentence about hashing becomes an edge.

Derivation sits in the entity and the application services, not in the repository.
`platform.persistence` may not import `platform.naming` — tach says so, and it is right:
translating rows into entities is not the same job as deciding what a paragraph means.

## Not wired into context expansion

Graph expansion in `docir context` still follows authored edges only, and this is a deferral
rather than a judgement. `benchmarks/run.py` cannot measure the alternative: its corpus
allocates ids at load time, so no fixture body can name one and the mention graph is empty
throughout the run. Wiring expansion to it would be a blind change to ranked output.

Deciding it needs a fixture whose documents cite each other in prose, the way
`benchmarks/chunking.py` needed one with real headings and sections over the model window
(issue-b1a6e57deeec). Until that exists, the honest answer is that nobody knows whether
expanding along mentions helps or dilutes.
