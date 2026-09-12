---
created: '2026-09-12'
description: '[[...]] cross-references resolve against ids, filename stems, title
  slugs and titles, render as the target''s current title, and the ones pointing at
  nothing are a Tier 1 warning; underneath, the six largest classes were split with
  every surface held byte-identical.'
id: rel-4acb78696bd6
related:
- adr-ae631a356639
- issue-7bc6f13c4d8c
- adr-a1754eb79fe7
- issue-55cc9295302a
status: published
tags: []
title: 0.26.0 — the link written in prose is a link docir reads
type: release_note
updated: '2026-09-12'
---

A body cites another document two ways, and docir read only one. `related:` frontmatter was
validated on write, reported by `dangling` and drawn on the graph; a `[[...]]` written
mid-sentence was parsed by nothing — not the renderer, not a check, not the index. It published
as literal brackets, and a retitle broke every inbound one in silence. This release makes the
prose link a link docir reads: it resolves, `docir build` renders it, and `docir check` names
the ones that point at nothing.

## Upgrade notes

- **No migration.** The index schema is unchanged, so `docir doctor` reports only
  `stale-index-build` until the first `docir reindex` after upgrading. `docir self upgrade`
  runs it and refreshes the generated instruction files, whose maintenance reference now
  documents `unresolved-link`.
- **A store that already writes `[[...]]` sees its broken ones on the next `docir check`.**
  They were broken before; this is the first build that says so. Each is a warning, so
  `docir check --strict` still passes, and `docir check --fix` leaves them — a target nobody
  can name is not a repair without a guess.

## The link written in prose is a link docir reads

A target may be a document id, a filename stem, a title slug or the title itself; a `.md`
suffix and a leading directory are stripped, `[[target|label]]` keeps the label and
`[[target#heading]]` links the anchor. Resolution reads every document, inactive and archived
included: a link to a resolved issue is a working link, and "not in the default `docir query`"
is never a reason to call one broken. An ambiguous target resolves to neither and names its
candidates.

The filename stem is carried as data rather than derived, because `docir update --set-title`
keeps the filename — so a retitled document's stem is the slug of a title it no longer has,
and the links written against it are exactly the ones that must keep working.

`docir build` renders a resolved link as the target's *current* title, so a retitle cannot
leave a link displaying a name no document has. An unresolved one stays the literal `[[...]]`,
like a dangling edge on the same page.

```
docir build
```

## `unresolved-link`, the prose half of `dangling`

`docir check` reports a `[[...]]` that resolves to nothing as `unresolved-link`, one finding
per (document, target). It is Tier 1 where `unresolved-mention` is Tier 2 because the two are
not the same defect: an id named in a sentence is a citation, while `[[...]]` is link syntax
with no second reading. The one false positive available is a body demonstrating the syntax,
and the scan skips code spans and fences. Prose links still feed no graph — `orphan` reads
`related:` alone — and nothing repairs one, so `docir check --fix` leaves it.

```
docir check
```

Verified by injecting each bug the guards claim to catch, and exercised against this
repository's own store through the daemon, the CLI, MCP and `docir build`; 0.25.0 reads a
store this build wrote and this build reads one 0.25.0 wrote, both clean.

## Underneath: six classes split by reason to change

`DocumentService`, `MaintenanceService`, `GraphChecker`, `cli/app.py`, the markdown file
store and `publishing/infra/rendering.py` were each split on the seam their own section
comments had drawn, and `build_mcp_server` went from 646 lines to 22. No `api.py` signature
and no `CONTRACT.md` moved. Every surface was held byte-identical rather than asserted: the
whole Typer tree, `tools/list`, every finding `docir check` reports against the released
0.25.0, all 422 files `docir build` produces from this store, and ranking under 300 randomised
differential trials. What the audit kept, and why `DocumentService` is not split further, is
on record as adr-a1754eb79fe7.

Full changelog: [CHANGELOG.md](https://github.com/l0kifs/docir/blob/v0.26.0/CHANGELOG.md)
