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

## Core loop

1. **Discover** before coding: `docir context "<task>"` → minimal ranked set.
2. **Read** the ones that matter: `docir get <id>`.
3. **Implement** (outside docir).
4. **Record** new decisions/issues: `docir add ...`.
5. **Update** status when resolving: `docir update <id> --status resolved`.
6. **Commit** the changed `docs/*.md` files (the index is derived; not committed).

## Read

| Command | Use |
|---|---|
| `docir context "<task>" [--limit N]` | Best first step: hybrid (lexical+semantic) ranking + 1-hop related docs. Graph-pulled items marked `via_graph`. |
| `docir get <id>` | Full doc (body included); works for any status. |
| `docir search "<text>"` | Full-text only. |
| `docir query --type decision --status accepted --tag auth` | Structured filter; repeatable `--type/--status/--tag`. |

Default read path **hides** resolved/archived docs. Add `--include-resolved`
(query/search/context) or use `docir get` to see them.

## Write

```
docir add --type decision --title "..." --description "..." \
  [--tags auth,api] [--related adr-0001,issue-0003] [--status ...] \
  (--stdin | --body "..." | --body-file f.md)

docir update <id> --status resolved             # metadata patch
docir update <id> --set-description "..."        # keep summary current on edits
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

## Checks & maintenance (non-blocking)

- `docir check` — Tier 1 warnings: cycles, orphans, layering, **dangling** `related` links, **duplicate ids**. Run before finishing.
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
