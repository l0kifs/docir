---
code:
- src/docir/modules/documents/domain/value_objects/doc_ref.py
- src/docir/entry_points/dispatch.py
created: '2026-08-25'
description: Why get takes several ids and id#heading addresses in one request, why
  the plural payload key rather than the result count decides the reply shape, and
  why an address that does not resolve is data instead of an error.
id: adr-fe7c91f61f32
owner: maintainer
related:
- kind: refines
  to: arch-1cfb1b212237
- issue-9509f9fa3631
- adr-927aa43d9635
status: accepted
tags:
- cli
- retrieval
title: The deep read is batched, and its shape follows the key
type: decision
updated: '2026-08-25'
---

## Context

Reading five documents cost five interpreters. issue-9509f9fa3631 measures the
floor: roughly half a second of a docir read is starting Python and importing
docir, while retrieval underneath it is flat from 25 to 2 000 documents. Every
ranked set an agent acts on is several documents, so the command that follows
`docir context` paid that floor once per body — five bodies for the price of
about five reads of one.

Over MCP the floor is already amortised, because the server is long-lived. The
same shape costs something else there: five tool calls are five model turns.

## Decision

`docir get` accepts several addresses in one request. An address is `<id>`, or
`<id>#<heading>` for one section of it — the form a ranked hit already hands
back as `matched_section` (adr-927aa43d9635). One unit of work answers all of
them, so the marginal cost of the second document is the body it carries.

The reply shape follows the payload key, not the number of results. `doc_id`
answers with the document object; `doc_ids` answers with `{documents, missing}`.
The CLI picks the key from how many ids were typed; every other client says
which it wants.

## Why the key, not the count

Deciding by count would make the reply shape depend on data. A caller that
batches would have to branch on how many results came back before it could read
one, and a list of one — the ordinary result of a loop that found a single
candidate — would arrive shaped like something else.

The rejected alternative was a second command. It reads cleaner per command and
costs more everywhere else: two names for one concept, which the corpus already
treats as a defect, plus a second MCP tool, a second federation entry, and a
decision for the caller on every read.

## Why a miss is data and a typo is not

A reference that does not resolve — no such document, or no such heading in it —
is reported in `missing` beside the documents that did resolve. The batch exists
because an agent has just ranked five documents; one of them having been deleted
since must not cost it the other four.

A *malformed* address still raises, and the asymmetry is the point. A miss is a
fact about the corpus that the caller could not have known. A typo is the
caller's own, and reporting it as a miss would let a mistyped id read as a
deleted document.

## What this does not change

The skeleton contract. `docir query`, `docir search` and `docir context` still
return no bodies. This widens how many bodies one *deep* read may name, never
which paths carry one.

Federation is unchanged in rule and only in rule: store priority is the single
read's — local first, then peers in declaration order, first match wins —
applied per address rather than once. A peer is asked for what nothing nearer
answered, and not asked at all once nothing is left.

## Consequences

The saving is the floor times the number of documents beyond the first, so it
grows with how many are read and is independent of their size. Measured in
issue-9509f9fa3631.

It is worth nothing to a caller reading one document, which is why `doc_id`
still exists rather than being folded into a one-element list.

The address grammar is a second place an id can be written, so it lives in one
value object and both the single and the batched read parse it there — the
argument adr-289e788719a7 makes about the id grammar itself.
