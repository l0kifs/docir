---
created: '2026-08-09'
description: 'What to run after a new docir release: the package, the derived index,
  and the generated files nothing refreshes for you.'
id: run-f4a756206fe0
owner: maintainer
related:
- run-30aceb4eacc6
- arch-90c90751344f
- adr-bd3a820cc57a
- adr-3a2d5ee7bc84
status: active
tags:
- release
- cli
- agents
title: Upgrade docir in a project
type: runbook
updated: '2026-08-09'
---

docir ships its schema, its agent instructions and its site templates inside the
package. A release can therefore change what a store enforces and what an agent
reads without a single file in your repository changing — there is nothing in
`git diff` to review. Some of that is applied for you on the next command; the
rest is this runbook.

Run it once per store. A machine has as many stores as it has `.docir/`
directories plus the global `~/.docir`, and each carries its own index, its own
daemon and its own schema baseline.

## What happens without you

- **Migrations.** The composition root runs Alembic on every command, so the
  first command after an upgrade brings the index schema forward.
- **The daemon.** It loads docir once and would otherwise keep answering from
  the old code — and a stale answer is indistinguishable from a correct one. The
  pid file records a `CodeStamp` (`__version__` plus the newest mtime across the
  package sources), and a client that does not match stops and respawns it.
- **Embedding vectors.** Each row records the model that produced it; a foreign
  `model_id` reads as dirty rather than as a vector to compare against, so a
  changed model recomputes on the next write instead of raising a dimension
  mismatch. Force it with `docir embed --flush` or `docir reindex --embeddings`.

## What you have to run

```bash
uv tool upgrade docir     # or: pipx upgrade docir, uv lock --upgrade-package docir
docir reindex             # once per store
docir check               # read the new warnings
docir agent update        # then commit the refreshed instruction files
```

### `docir reindex` — the only mandatory step

It is the only writer of the schema baseline the index records, so until it runs
`check` reports no `schema-drift` at all: absent means *unknown*, not unchanged.
It also raises the id counter to what is on disk, which is what a fresh clone
needs — the index is gitignored, so a clone has no index and every read answers
nothing until it is built. `check` does not warn about that state — an empty index
reports `no structural issues`, exactly like a healthy one. `build` is the one
command that says so.

There is deliberately no `docir accept-schema` verb. `reindex` is already the
"make the derived state agree with the sources" command, and a separate
acknowledgement would be a ritual whose only effect is to silence a report.

### `docir check` — new warnings are expected

`missing-required`, `unknown-relation-kind`, `unknown-type` and `schema-drift`
can all appear on a corpus that was clean yesterday. Every one is a `warning`,
so `--strict` stays green and CI does not go red on the release that moved a
rule: the documents are untouched and it is the *rule* that moved. Deal with
them as documents (`docir update <id> ...`) or as schema (`docs-schema.yaml`),
then reindex to re-baseline.

`DOCIR_SCHEMA_NOTICE=1` prints the drift on stderr after every command, for the
change nobody will run `check` to discover.

### `docir agent update` — the files nothing tracks for you

`.claude/skills/docir/SKILL.md` and the docir block in `AGENTS.md` are generated
from a template inside the package and stamped `<!-- docir:vX -->`. They are
committed files, so refreshing them is a commit, and nothing detects that they
are behind: `check` covers the corpus, not the generated instructions. docir
0.11.0 shipped with its own skill file still claiming v0.10.0.

## If it applies to you

- **`docir init --force`** regenerates the store's `.gitignore`, which is a
  constant in the package and can gain entries between releases. A
  `docs-schema.yaml` you have edited is preserved and reported, not replaced —
  `--force-schema` is what replaces it.
- **`docir build --out <dir>`** — the site templates ship in the package, so a
  published corpus is only as new as its last build.
- **MCP clients** hold a long-lived server process: restart the client so it
  re-execs the new binary. One spawned as `uvx docir mcp serve` resolves from
  uv's cache, so name the version (`uvx docir@0.11.0 mcp serve`) when it matters.
- **CI** installs docir on its own; pin the version there and bump it in the
  same commit, or the gate runs a different docir from the one you tested with.

## Verify

```bash
docir daemon status       # reports the build being served
docir query --limit 1     # a non-empty answer means the index is populated
docir check --strict      # exit 0
```
