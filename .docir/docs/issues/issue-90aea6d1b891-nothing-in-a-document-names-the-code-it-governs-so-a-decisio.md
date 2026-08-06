---
code:
- src/docir/modules/documents/domain/services/code_globs.py
- src/docir/platform/filesystem/code_matcher.py
created: '2026-08-06'
description: No frontmatter field points at code, and the schema's 'required' hook
  that appears to allow one is unsatisfiable — which blocks enforcement against code
  and AST-anchored staleness alike.
id: issue-90aea6d1b891
owner: maintainer
related:
- ref-a6db21f52427
- adr-bd7c4f3c5764
- arch-0a3c2d6d54a6
status: resolved
tags:
- material
- schema
- staleness
title: Nothing in a document names the code it governs, so a decision cannot be found
  from, or checked against, the codebase
type: issue
updated: '2026-08-06'
---

**Class:** missing · **Severity:** material
**Source:** ref-a6db21f52427 (competitive survey, gap 7 — "open, the enabler")
**Step:** binding a decision to the code it governs · **Frequency:** every decision about code

## Finding

No frontmatter field names code. `Document` carries id, title, description, type, status, created,
updated, tags, related, archived, body, path, owner, verified — and nothing else
(`document.py:23-39`). The markdown store writes exactly that key set and parses exactly that key
set, so a hand-added `code:` key is silently dropped on the next write
(`markdown_store.py:118-160`).

## What happens today

An ADR says "SQLite is a derived index"; nothing connects it to `platform/persistence/`. A reviewer
touching that directory cannot ask "which decisions govern this?", and `docir check` cannot notice
that the governed code moved or vanished. archgate binds an ADR to an executable rule that fails
CI; trackfw enforces ADR → requirement → roadmap; Log4brains and adrkit at least derive metadata
from git log. docir validates the document graph against itself and stops there.

The schema appears to offer a way in and does not. `required:` is documented as "extra frontmatter
fields this type must carry" (`default_schema.py:80-81`) and the loader accepts any name
(`schema_loader.py:290-292`), but `validate_required_fields` reads it with `getattr(document, name,
None)` (`validation.py:33-42`) — a name that is not an entity attribute is missing for every
document, forever. Verified in a throwaway store: a type declaring `required: [code]` rejects every
`add` with `required field 'code' is missing or empty for type 'probe'`, and no CLI flag can supply
it. So this is an entity + file-store change, not a schema-only one. (That `required` accepts
unsatisfiable names is a separate defect; it is recorded here as evidence, not fixed here.)

## Impact

This is the "why is the document worth writing" argument the product does not make. It also blocks
two other things: gap 6 (enforcement against code) has nothing to bind a rule to, and the
AST-anchored staleness signal adr-bd7c4f3c5764 defers has no anchor to hang on. A decision whose
code was deleted a year ago reads exactly like one that is still in force.

## Proposed default

Data first, machinery later — the shape every other docir capability took (staleness, typed edges,
profiles):

1. Optional `code:` in frontmatter: a list of repo-relative globs, on `Document`, the markdown
   store and the index. Tier 0 validates the *shape*, not whether the target exists — a write must
   not fail because a branch has not created the file yet.
2. A Tier 1 `check` finding when a governed glob matches nothing on disk. `warning`, not `error`:
   code moving is normal and the corpus is not broken by it (`graph_checks.ERROR_KINDS`).
3. Only then consider gap 6. With 1 and 2, "which decisions govern what this PR touched" is a query,
   which is most of what an executable-rule engine would be wanted for, without the engine.

Not proposed: deriving `commit`/`pr` from git log. That makes the index depend on repository
history rather than on the files, which the "files are canonical, index is derived" thesis does not
cover — a shallow clone would rebuild a different index from the same documents.

## Resolution

FIXED 2026-08-06, as proposed, in the three steps the proposal set out.

**1 — the data.** `Document.code` is a tuple of repo-relative globs, written to frontmatter only
when non-empty (the rule `owner`/`verified` follow), parsed back, and indexed in `document_code`
(migration `0004`) — a child table like `document_tags`, because the value is a set and the
question asked of it reads the patterns. It rides on `DocumentView` *and* `DocumentSummary`, so
"does this document concern the code I am about to change" is answerable from a skeleton. Set
with `add --code` / `update --set-code`, on the CLI and over MCP. `content_hash` sorts the globs,
for the reason it already sorts tags: the file keeps the author's order and the index returns
them sorted, and without the sort a reindexed document read as hand-edited, so `--replace-body`
refused a write that loses nothing.

Tier 0 validates the **shape only** — absolute path, `..` segment, backslash separator, empty
entry, each a pattern that can never match — and accepts one that matches nothing today. That is
the load-bearing non-check: making it an error would teach authors to omit the field, which is
the state this issue exists to leave.

**2 — the Tier 1 check.** `docir check` reports `unmatched-code` when a governed glob stops
matching, as a `warning`: the corpus is intact, a pattern is out of date. It is skipped entirely
when the store has no repository above it (`Settings.code_root`, the `.git` walk
`is_unintended_global_fallback` already used, started at the store) — a global `~/.docir` has no
tree to resolve a repo-relative pattern against, and reporting every pattern there as missing is
the "warning that fires on correct usage" failure the cycle and layering checks were each fixed
for. `check --fix` deliberately leaves it: only a human knows whether the glob is stale or the
document is.

**3 — the reverse query.** `docir query --code <path>` (repeatable; any match counts) lists the
documents governing a file, so `docir query --code $(git diff --name-only main)` is the set of
decisions a branch must be read against. Matching is **textual, not a filesystem walk** — the
branch that *deletes* a file is exactly when its decisions must be re-read, and a filesystem
match answers "nothing" there. Like `--stale` it is a post-SQL predicate applied *before* the
limit, sharing one scan loop with it. A document governing a directory governs the files in it: a
miss costs an unread decision, a false hit costs a glance.

Dogfooded the same day: 28 of docir's own documents now declare what they govern, `docir check`
reports nothing, and querying the files of the branch that built this returns the MCP, `init` and
agent-scaffolding ADRs. One lesson the design did not predict — `arch-1cfb1b212237` governs
`src/docir/**` and so answers *every* query; that is true and still costs the reader something.

**Deliberately not done.** No `commit`/`pr` field derived from git log: it would make the index
depend on repository history rather than on the files, and a shallow clone would rebuild a
different index from the same documents. Enforcement against code (gap 6 of ref-a6db21f52427) is
still not built, but it is no longer blocked — a rule now has something to bind to, and most of
what it was wanted for is answerable by the query. The `required:` defect found while writing
this is issue-e3c4dfad4f7b, filed rather than fixed here.

## Actors affected

- ACT-001 AI coding agent
- ACT-002 repository maintainer / developer
- ACT-007 document owner / steward

## Evidence

- `src/docir/modules/documents/domain/entities/document.py:23-39`
- `src/docir/platform/filesystem/markdown_store.py:118-160`
- `src/docir/modules/documents/domain/services/validation.py:33-42`
- `src/docir/modules/documents/infra/schema_loader.py:290-292`
- `src/docir/modules/documents/domain/services/graph_checks.py:42`

---

Opened from the 2026-08-06 re-verification of ref-a6db21f52427, where gaps 6 and 7 were the only
two of the twelve still worth building.
