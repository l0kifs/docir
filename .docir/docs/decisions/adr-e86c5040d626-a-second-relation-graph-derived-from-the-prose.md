---
code:
- src/docir/platform/naming/__init__.py
- src/docir/modules/documents/domain/entities/document.py
- src/docir/platform/persistence/repositories.py
- src/docir/modules/documents/domain/services/graph_checks.py
created: '2026-08-17'
description: Why ids named in a body become mention edges, why only the orphan check
  reads them, why they stay out of frontmatter, and what following them cost in the
  benchmark.
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

## Context expansion follows them, and that was measured

Graph expansion in `docir context` follows mentions as well as authored edges. That was not
obvious, and it was measured rather than assumed.

`benchmarks/run.py` could not measure it: its corpus allocates ids at load time, so no fixture
body can name one and the mention graph is empty for the whole run — the wrong-instrument trap
issue-b1a6e57deeec describes. `benchmarks/mentions.py` is the instrument, with a corpus whose
bodies carry `{key}` placeholders substituted once every document has an id.

## What it measured

Against the shipped embedder, over 19 documents and 15 tasks at the default `expand=2`:
recall@5 rose from 0.84 to 0.93 and precision from 0.33 to 0.37, with MRR unchanged at 0.86.
One task of fifteen regressed.

Authored edges are still ordered first. A `supersedes` is a claim about correctness; a citation
in a paragraph is a claim about nothing, so it yields when the budget is tight.

## The budget, and a claim this corrected

Sweeping `expand` over 0..3 on the same fixture showed `expand=1` capturing the entire gain —
1 and 2 are indistinguishable at 0.93/0.37 — so the shipped default of 2 is undistinguished
rather than evidenced.

It also corrected the reason MRR held. The first version of this decision said expansion could
never displace a ranked hit. It can: `seed_budget = limit - expand`, so at `expand=3` with
`limit=5` only two ranked hits precede the neighbours, a relevant document that ranked third is
pushed behind the graph, and MRR falls to 0.83 while precision rises to 0.40. MRR holding at
`expand=2` is a property of the budget, not of expansion.

## Two things the benchmark had to fix about itself

It mints sequential ids, unlike `run.py`, which prices what random ones cost to read. Random
ids move ranking ties, and the same code scored 0.79 and 0.81 on consecutive runs — a baseline
that wanders cannot settle a small difference.

And it derives the prose-linked/not grouping from the corpus rather than from a hand-written
label. The first version asked the fixture's author to label the fixture, and the labels were
wrong in the direction that flattered the feature: they hid that mentions also restore
*backwards* reachability for non-successor edges like `refines`, which is a second real effect
and was being read as the fixture leaking.

## An unresolved mention is not a finding, and this was measured

The obvious next check is a Tier 1 warning for an id named in prose that resolves to nothing —
a typo, or a document deleted since. It was measured against this corpus before being built,
and the measurement rejected it.

47 mentions here are unresolved, across 12 distinct ids. **All twelve are documentation
examples**: `adr-0001`, `adr-0002`, `adr-0003`, `adr-0007` and `issue-0001` are the canonical
sequential ids used in prose that explains the id format, and `adr-3f9a2b1c7d4e`,
`adr-012345678901` and the rest are the example random ones. Not one is a typo or a dead
reference.

So the check would fire 47 times on a healthy corpus, every time a false positive, and its
loudest sources would be the architecture documents that explain what an id looks like — the
documents doing their job. That is issue-9cb85759076d's failure exactly: a warning that fires
on correct usage teaches people to stop reading `docir check`, and the gate that gets switched
off takes duplicate-id detection with it.

### The obvious discriminator makes it worse

Ignoring ids inside code spans and fenced blocks sounds like it separates an example from a
citation. Measured on the same corpus: 20 of the 47 unresolved mentions sit outside code
anyway, so the noise survives — and 56 **resolved** mentions exist only inside code spans, so
the filter would delete 12% of the working graph and hand back the `orphan` false positives
those edges are there to prevent.

The check is not blocked on a better filter. It is blocked on the fact that naming an id
without linking to it is a normal, correct thing for a document to do.
