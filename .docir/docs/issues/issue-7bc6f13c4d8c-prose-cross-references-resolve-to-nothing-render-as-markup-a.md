---
code:
- src/docir/platform/naming/links.py
code_baseline:
  src/docir/platform/naming/links.py: 5c7ca5dd25fb
created: '2026-09-11'
description: '162 prose links in a maintained store were parsed by nothing: build
  published brackets, a retitle broke inbound links in silence, and finding the one
  that was broken took four hand-written passes.'
id: issue-7bc6f13c4d8c
owner: maintainer
related:
- adr-ae631a356639
status: resolved
tags:
- cli
- integrity
- retrieval
title: Prose cross-references resolve to nothing, render as markup, and no check sees
  them
type: issue
updated: '2026-09-11'
---

**Class:** missing · **Severity:** material
**Flow:** the read path (prose cross-references) · **Step:** rendering a body, and `docir check`
**Frequency:** every `[[...]]` ever written — 162 occurrences across 94 targets in the reporting store

## Finding

Documents cross-reference each other two ways and docir read only one. `related:` frontmatter is
resolved, validated, checked and drawn. `[[...]]` written in prose was touched by nothing: not
parsed, not resolved, not rendered, not checked. `grep -rn '\[\['` over the source returned zero
hits.

## What happens today

REPORTED as GitHub issue #9 against 0.25.0, REPRODUCED on the same build. Three failures, and
the first is worse than reported:

```
[[adr-fea4a96ca90c]]                      -> [[<a href=…><code>adr-fea…</code></a>]]
[[adr-fea4a96ca90c-hub-api-reads-…]]      -> [[<a …>adr-fea…</a>-hub-api-reads-…]]
[[token-issuer-epoch-drift]]              -> literal text
```

The bracketed id matched the bare-id linkifier, so `build` published a link wearing two stray
brackets, and the filename-stem form published as a link with the slug hanging outside it.
`docir check` and `docir lint --deep` reported nothing about any of them.

## Impact

A retitle silently breaks every inbound link: `update --set-title` keeps the filename, so the
old slug still names a file while no longer naming a title, and nothing reports it.

The reporter found one broken link in 162 occurrences, by writing a throwaway script, in four
passes — two of which were wrong because `query` excludes inactive documents by default and a
link to a `resolved` document is not broken. That is the measure of how legible this is: four
attempts by the person who wrote the links, in the corpus he maintains. The yield is small and
the failure is silent, permanent, and reads as fact to anyone who does not go and check.

## Actors affected

- AI coding agent writing cross-references into bodies
- repository maintainer reading the published site
- anyone validating links outside docir, who must reimplement a rule docir had not defined

## Evidence

- `src/docir/modules/publishing/infra/rendering.py` (`_linkify_doc_ids`, as it was)
- `src/docir/modules/documents/domain/services/graph_checks.py`
- https://github.com/l0kifs/docir/issues/9

## Resolution

FIXED. `platform.naming.links` owns one resolution rule — id, filename stem, title slug, title —
read by both sides: `publishing` renders the resolved ones as links carrying the target's current
title, and `docir check` reports the rest as `unresolved-link`, a Tier 1 warning. Resolution
reads inactive and archived documents, which is the half the hand-written scripts got wrong.
Links inside code spans and fences are skipped, so a body explaining the syntax is not a finding.

Prose links still feed no graph: `orphan` reads `related:` alone. The reasoning, including why
this is Tier 1 where `unresolved-mention` is Tier 2, is adr-ae631a356639.

Verified by injecting the bug: with resolution restricted to the default `query`, the check
reports the link to the `resolved` issue as broken — the reporter's own second pass — and with
code skipping removed it reports this repository's two syntax examples.
