---
name: docir
description: Use docir to read and write this project's git-backed design docs — decisions/ADRs, issues, architecture notes — instead of editing markdown by hand. Trigger whenever the repo uses docir (a `docir` command is available, a `.docir/` store exists in the repo or `~/.docir`, or docs carry docir frontmatter) and you are about to implement a feature (pull relevant decisions first), record or resolve a decision/issue/ADR, search project knowledge, or restructure/migrate existing markdown docs into docir. Covers the read path (`docir context/get/search/query`) and the write path (`docir init/add/update/archive`) — every doc write MUST go through the CLI.
---

# docir — Agent Guide

Git-backed markdown docs (decisions, issues, architecture) with a derived index
(full-text + relation graph + semantic search). Files are the source of truth;
every write goes through the `docir` CLI to keep frontmatter/schema valid.

Prefix all commands with `docir`. Add `--json` for machine-readable output.

## When to use

Use docir whenever this repo manages design docs with it (a `docir` command, a
`~/.docir` dir, or `docs/*.md` with docir frontmatter are present):

- **Before implementing** a feature — pull the relevant decisions/issues first.
- When **recording** a new decision/ADR or issue you discovered.
- When **resolving or updating** an existing doc.
- When **searching** project knowledge.

docir is the ONLY sanctioned way to read/write these docs — **never edit the
markdown files by hand.**

## Set up in a project

docir keeps docs in **one store**. By default that is the global `~/.docir`
store (shared by every project). To scope docs to *this* repo, run **`docir
init`** once — it creates a `.docir/` store in the repo that every `docir`
command auto-discovers by walking up from the working directory (the way git
finds `.git`):

```
docir init                       # create ./.docir (default profiles: software)
docir init --profiles research   # choose a schema profile that fits the docs
```

Commit `.docir/docs/` and `.docir/docs-schema.yaml`; the derived index is
gitignored for you. If you skip `docir init`, docs go to the global `~/.docir`
store — fine for personal notes, but **not** what you want for a repo whose docs
should live with the code. Check where you are with `docir query --limit 1` (it
operates on the discovered store).

## Core loop

1. **Discover** before coding: `docir context "<task>"` → minimal ranked set.
2. **Read** the ones that matter: `docir get <id>`.
3. **Implement** (outside docir).
4. **Record** new decisions/issues: `docir add ...`.
5. **Update** status when resolving: `docir update <id> --status resolved`.
6. **Commit** the changed docs under the store (`.docir/docs/*.md` in a project;
   the index is derived and gitignored).

## Read

| Command | Use |
|---|---|
| `docir context "<task>" [--limit N]` | Best first step: hybrid (lexical+semantic) ranking + 1-hop related docs. Graph-pulled items marked `via_graph`. |
| `docir get <id>` | Full doc (body included); works for any status. |
| `docir search "<text>"` | Full-text only. |
| `docir query --type decision --status accepted --tag auth` | Structured filter; repeatable `--type/--status/--tag`. |

**Two-tier read (skeleton → body).** `context` / `query` / `search` return
*skeletons* — id, title, description, tags, typed `related`, `owner`,
`verified`, `stale` — **but not the body**. Scan those to judge relevance, then
pull only the bodies you need with `docir get <id>`. This is the cheap path;
never dump every body.

Default read path **hides** resolved/archived docs. Add `--include-resolved`
(query/search/context) or use `docir get` to see them.

## Write

```
docir add --type decision --title "..." --description "..." \
  [--tags auth,api] [--related adr-0001,arch-0002:implements] [--status ...] \
  [--owner platform-team] (--stdin | --body "..." | --body-file f.md)

docir update <id> --status resolved             # metadata patch
docir update <id> --set-description "..."        # keep summary current on edits
docir update <id> --set-related adr-0001:supersedes   # replace typed edges
docir update <id> --set-owner platform-team     # assign a steward
docir update <id> --verified                     # stamp today as last-verified
docir update <id> --append-section "Resolution" --body "Fixed in PR 42"
docir update <id> --replace-section "Context" --body "..."
docir update <id> --replace-body --force --body "..."   # full overwrite
docir archive <id> | docir unarchive <id>
docir delete <id> [--force]
```

- Prefer `--stdin` for multi-line markdown bodies (no shell-escaping).
- Body edits, safest→riskiest: `--append-section` (default choice) →
  `--replace-section` → `--replace-body` (needs `--force`; fails "stale write"
  if the file changed on disk — `docir get` first).
- When a body edit changes what the doc is about, update `--set-description`
  in the same call; it drives search quality.

## Migrating existing docs into docir

To restructure a repo's existing markdown (design notes, ADRs, RFCs) into docir,
work in this order — the constraints below make any other order fail:

1. **Init first** and pick a fitting profile (see *Set up in a project*). Default
   types are `decision`/`issue`/`architecture`; enable `research`/`ops`/`legal`
   in `docs-schema.yaml`, or add inline `types:`, for docs that don't fit — a doc
   whose `type` isn't in the schema is a Tier 0 error.
2. **Register tags** you'll apply: `docir tag add <key> --description "..."`
   (every `--tags` key must exist first).
3. **Add each source doc one at a time** (there is no bulk import). Map it to a
   type and write a real `--description` (it drives search); strip any existing
   YAML frontmatter from the body first:
   ```
   docir add --type decision --title "..." --description "..." --stdin < old/adr-001.md
   ```
   **Never invent ids** — docir assigns them (`adr-0001`, …). Record the returned
   id for each source file so you can link them next.
4. **Wire relationships in a second pass**, after every doc exists and has an id:
   `docir update <id> --set-related <other-id>:supersedes`. Links can't be set in
   step 3 because every `--related` target must already exist.
5. **Validate**: `docir check --strict` — it flags dangling links, duplicate ids,
   unknown types, and stale docs. Fix, then remove or keep the originals.

## Typed edges (`related`)

Each `related` entry is a **typed edge**: a target id plus a relation *kind*.

- Compact form: `<id>` (defaults to `relates_to`) or `<id>:<kind>` —
  e.g. `--related adr-0007:supersedes,issue-0003:depends_on`.
- Core kinds: `relates_to` (default), `supersedes`, `depends_on`, `implements`,
  `contradicts`, `refines`. An unknown kind is a Tier 0 error (like an unknown
  tag). Some types constrain which kinds/targets they allow.
- Prefer a typed edge over prose when a real relationship exists — traversal is
  exact and cheap. Model "A replaces B" as `A --supersedes--> B` (not only a
  status change on B).

## Staleness (`owner` / `verified`)

For docs that need periodic human re-confirmation, set an `--owner` and, when you
(or a human) confirm a doc is still correct, run `docir update <id> --verified`.
A type's review cadence (`review_days` in the schema) drives a non-blocking
`stale` warning in `docir check` and a `stale` flag on read views. Editing the
body does not equal verifying it — `--verified` is the explicit signal.

## Tags (must exist before use)

```
docir tag add auth --description "Authentication, tokens, sessions."
docir tag list
docir tag rename auth authn         # rewrites every referencing doc
docir tag rm auth [--force]         # --force strips it from docs; else blocked
```

## Hard rules (Tier 0 — these fail the write)

- Never edit `docs/*.md` directly. Always use the CLI.
- `id` is auto-assigned `<prefix>-NNNN`; never invent one. Prefixes: decision→`adr`, issue→`issue`, architecture→`arch`.
- Every `--tags` key must be registered first; every `--related` id must exist.
- `--status` must be a valid transition (see below); use `--override` to force.

## Types & statuses (default schema)

| type | statuses (→ = allowed transition) | hidden by default |
|---|---|---|
| decision | proposed → accepted / rejected; accepted → superseded / rejected | rejected, superseded |
| issue | open → resolved | resolved |
| architecture | draft → active → deprecated | deprecated |

The default schema is the frozen **core** (`decision`) plus the **software**
profile (`issue`, `architecture`). Other bundled profiles add domain types —
`research` (hypothesis/experiment/finding), `ops` (runbook/incident/postmortem),
`legal` (policy/contract/obligation) — enabled per install with
`profiles: [..]` in `~/.docir/docs-schema.yaml`.

## Checks & maintenance (non-blocking)

- `docir check` — Tier 1 warnings: cycles, orphans, layering, **dangling** `related` links, **duplicate ids**, **stale** docs (past their review cadence), **unknown type** (a doc whose `type` isn't in the active schema — e.g. its profile was disabled). Run before finishing.
- `docir check --strict` — exits nonzero on any issue; use as a **CI / pre-merge gate** to catch duplicate ids or dangling refs a branch merge introduced before they reach `main`.
- `docir lint --deep` — Tier 2 advisories (duplicate content, oversized docs).
- `docir reindex [--changed]` — after a doc file was hand-edited, merged, or freshly cloned.

## Working across git branches

Only `docs/*.md` + `tags.yaml` are committed; the index is derived and gitignored.
After any merge/pull: `docir reindex --all` then `docir check --strict`. If several
people author docs on concurrent branches, set `id_style: random` per type in
`docs-schema.yaml` — it mints collision-resistant ids (`adr-3f9a2b1c7d4e`) so two
branches never allocate the same id. The default `sequential` style (`adr-0007`)
is only collision-free within one shared index.

## Notes

- Exit codes are nonzero on error (2=validation, 4=not-found, 5=conflict, 6=stale). With `--json`, errors go to stderr.
- Semantic vectors are computed async; add `--wait-embeddings` to a write (or `docir embed --flush`) if you must `context`-search immediately after.
- All state lives under `~/.docir` (override `DOCIR_HOME`); the index is disposable and rebuildable from files.
