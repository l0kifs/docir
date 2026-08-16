---
code:
- src/docir/modules/documents/domain/services/schema_shape.py
- src/docir/entry_points/cli/app.py
created: '2026-08-08'
description: schema-drift reports a schema change after the fact; nothing renders
  the effect of an edit beforehand, and the file's meaning is not its text because
  the core and profiles merge into it.
id: issue-3678c897295f
owner: maintainer
related:
- adr-2a3f625bb2f8
- adr-bd3a820cc57a
- issue-d891ab5501e6
- adr-dbe6633405ca
status: resolved
tags:
- cosmetic
- schema
title: No way to see what a docs-schema.yaml edit will change before it lands
type: issue
updated: '2026-08-16'
---

**Class:** missing · **Severity:** cosmetic
**Source:** schema-evolution investigation, 2026-08-07 (the gap `schema-drift` left)
**Step:** editing `docs-schema.yaml` · **Frequency:** every schema edit, which is rare by design

## Finding

`schema-drift` answers "what changed under me", after the fact. Nothing answers **"what am I about
to change"** — there is no way to see the effect of a `docs-schema.yaml` edit before it lands.

The file's meaning is not its text. The frozen core and the bundled profiles are merged into it on
every command, so a one-line edit can move a great deal: `profiles: [software]` ->
`profiles: [software, research]` adds three types, three prefixes and three cadences, none of
which appear in `git diff`. That is the same gap issue-d891ab5501e6 closed for upgrades, on the
other side of the write.

## What happens today

`docir schema show` prints the merged result, but only the current one — there is nothing to
compare it against. The workaround is to commit the edit, run `docir reindex`, and read the
`schema-drift` findings, which puts the review *after* the change is in history. `docir schema
validate` answers a different question: whether the file loads at all.

## Proposed default

`docir schema diff [<ref>]` — render the merged schema as it is now and as it was at a git ref
(default `HEAD`), and print the same lines `schema-drift` prints. One renderer
(`domain/services/schema_shape`) already produces both halves; only reading the old file is new.

## Argument against, which is the reason this is filed rather than built

**It would make docir read git objects, which it has never done.** `Settings.code_root` locates a
`.git` *directory* to resolve repo-relative globs, and `docir check`'s `unmatched-code` walks the
working tree — neither reads a git object, a ref or an index. `docir build`, `query --code` and
the CI notice all take the working tree as it is; the README's own example pipes `git diff
--name-only` **in from the shell** rather than calling git itself, which is the current stance
stated as clearly as it can be.

Adding this means either shelling out to `git` (a new external dependency, and a new failure mode
in a store that need not be in a repository at all — the global `~/.docir` is not) or vendoring an
object reader for one command. Against that: the schema is edited rarely, `git stash` + `docir
schema show` answers the same question in two commands, and the cost of getting it wrong is now
bounded, since `schema-drift` reports the change on the very next `check`.

## Actors affected

- ACT-002 repository maintainer / developer

## Evidence

- `src/docir/modules/documents/domain/services/schema_shape.py` — the renderer and the differ both exist
- `src/docir/config/settings.py:124` — the only mention of `.git`, and it is directory detection
- `src/docir/entry_points/cli/app.py:529` — the shell pipes git in; docir does not call it

## Resolution

Half of this is built: `docir schema validate` now reports what the schema in
the file costs the corpus, which is the question that actually gets asked while
editing it. See adr-dbe6633405ca for the design and for the properties it has to
keep (files not index, no database, no exit code change).

The other half — comparing against the schema at a git ref — stays unbuilt, for
the reason argued above: it needs docir to read git objects, which it has never
done. Nothing in the built half needs history, since the schema in the file and
the documents on disk are both present.
