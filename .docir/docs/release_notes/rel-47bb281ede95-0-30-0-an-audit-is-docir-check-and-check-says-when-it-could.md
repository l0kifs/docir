---
created: '2026-09-28'
description: An agent audits a store by trusting docir check's findings at under half
  the cost of auditing without docir, and a check that could not resolve code globs
  says so instead of reading clean.
id: rel-47bb281ede95
related:
- adr-3c5eb1ff3800
- adr-1cccd77cb023
- adr-31aa7aa60d11
- issue-8951b5a70e9d
- issue-2bb30af6216d
- issue-413546da5db7
- issue-f0b537bde01a
status: published
tags: []
title: 0.30.0 — an audit is docir check, and check says when it could not look
type: release_note
updated: '2026-09-28'
---

## 🎯 The release

**An audit is `docir check` — and `check` now says when it could not look.**

Asked to audit a store, an agent with docir installed either never loaded the skill — its
description named implementing, recording, searching and migrating, not checking — or loaded
it, ran `docir check`, and then re-derived every finding with grep and Python anyway. That
cost as much as auditing without docir at all.

### The skill says the findings are the answer

The installed skill now loads for checking the docs, and tells the agent that `check` applies
each rule to every file, which of a `dangling` finding's two ids is the document, and what a
clean `check` does *not* mean.

Measured with `benchmarks/agent_tokens.py` on this repository's store with five planted
defects — a dangling edge, a duplicate id, a `depends_on` cycle, an overdue review, a file that
does not parse: 12 of 12 audit runs loaded the skill and named exactly the planted defects, at
a median of $0.090–0.116 per audit against $0.23–0.38 for an agent without docir
(claude-sonnet-5, 93 to 259 documents, 2026-09-28). Take it with:

```bash
docir agent update
```

### A clean `check` now means something

With no git repository above the store, there is no tree to resolve a `code:` glob against, so
`unmatched-code`, `code-unwatched`, `code-changed` and `code-drifted` all went silent — and an
empty code section read exactly like a tree where nothing had moved. A store whose documents
declare `code:` now gets one `code-unchecked` warning saying so. A store that declares no code,
like the ordinary global one, says nothing.

## 🎯 Also in this release

- **The `duplicate` finding says what to do with it.** `docir lint --deep` names two unlinked
  documents that are the same document written twice; the skill, the docstring and the MCP
  tool now say the answer is an edge, not a delete. The skill also tells an agent to run
  `docir context` over a description before `docir add`, and to record a disagreement it finds
  by reading as a `contradicts` edge.
- **Measured and rejected: detecting contradictions** (adr-3c5eb1ff3800). The embedder scores
  subject, not stance — a claim and its own negation score up to 0.983 — so no threshold both
  reaches this corpus's recorded contradictions and stays readable.

## 🐛 Bug fixes

Each of these was docir reporting success on something it had not done.

- **A repeated list flag keeps every value.** `docir add --type decision --title T --code "a/**"
  --code "b/**"` wrote only `b/**`, and said nothing. The seven write-side list flags — `add
  --tags/--related/--code`, `update --set-tags/--set-related/--set-code` and `init --profiles` —
  now repeat the way every read-side one already did; each occurrence is still comma-split.
- **A file that lists one tag, glob or edge twice is read once.** A repeated tag failed every
  `docir reindex` with a raw `IntegrityError`; a repeated glob made `--replace-body` refuse the
  document as changed on disk, permanently. `docir check` now names such a file as
  `repeated-entry`, and `docir check --fix` rewrites it without the repeat and without moving
  `updated`.
- **`docir self upgrade` no longer calls a stalled upgrade "already the newest build".** An
  installer can exit 0 having changed nothing — a `uv tool` receipt pinned to an exact version,
  a pip held back by a constraint file. The version is now read back after the install; when
  it did not move, docir says so and quotes what the installer printed, which is where the
  cause is.

## ⬆️ Upgrading

- Run `docir agent update` so the installed skill loads for audits.
- A wrapper that passed a list flag twice and relied on the last one winning now gets both.
- If `docir check` reports `repeated-entry`, `docir check --fix` repairs it.

## 🔗 Full changelog

See [CHANGELOG.md](https://github.com/l0kifs/docir/blob/v0.30.0/CHANGELOG.md)
