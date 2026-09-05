<!-- docir:v0.24.0 — generated file, do not edit by hand; refresh with `docir agent update` after upgrading docir -->
# Setting up and adopting docir

Putting a repo on docir, moving its existing markdown in, and keeping branches
and fresh clones consistent. Read [`SKILL.md`](../SKILL.md) first for the
everyday loop.

## Contents

- Set up in a project — `docir init`, profiles, which store a write lands in
- Migrating existing docs into docir — the five-step order, and why there is no bulk import
- Working across git branches — what is committed, and `id_style`

## Set up in a project

docir keeps docs in **one store**. By default that is the global `~/.docir`
store (shared by every project). To scope docs to *this* repo, run **`docir
init`** once — it creates a `.docir/` store in the repo that every `docir`
command auto-discovers by walking up from the working directory (the way git
finds `.git`):

```
docir init                       # create ./.docir (default profiles: software)
docir init --profiles research   # software | research | ops | qa | legal (CSV)
```

Commit `.docir/docs/` and `.docir/docs-schema.yaml`; the derived index is
gitignored for you. Re-running `docir init` is safe — it writes only what is
missing. `--force` regenerates the `.gitignore` and an *unedited* schema; a
schema you have customised is kept and reported (`schema_preserved`), because it
cannot be rebuilt from the documents. Never reach for `--force-schema` unless
you intend to throw that file away. If you skip `docir init`, docs go to the global `~/.docir`
store — fine for personal notes, but **not** what you want for a repo whose docs
should live with the code.

If your client reaches tools over MCP rather than a shell, `docir mcp serve`
exposes this same vocabulary as MCP tools (`docir_context`, `docir_get`,
`docir_add`, …) through the same dispatcher — everything in this guide still
applies, one name per command. It is written for the CLI.

**Every write reports the `store` it landed in.** Check it: `path` is relative to
the store, so it reads as repo-local wherever the store actually is. If `store`
points at a home directory while you are working in a repo, the docs are going
somewhere nobody else will see — `docir` also warns on stderr in exactly that
case. Run `docir init` first.

## Migrating existing docs into docir

To restructure a repo's existing markdown (design notes, ADRs, RFCs) into docir,
work in this order — the constraints below make any other order fail:

1. **Init first** and pick a fitting profile (see *Set up in a project*). Default
   types are `decision`/`issue`/`architecture`/`release_note`; enable
   `research`/`ops`/`qa`/`legal` in `docs-schema.yaml`, or add inline `types:`
   (see `reference/schema.md`), for docs that don't fit — a doc whose `type` isn't
   in the schema is a Tier 0 error. Confirm with `docir schema show`.
2. **Register tags** you'll apply: `docir tag add <key> --description "..."`
   (every `--tags` key must exist first).
3. **Read each source file, then add it — one at a time.** There is deliberately
   no bulk import: adoption is a *judgement* task, not a conversion task, and a
   command that turned N files into N documents would look finished while being
   wrong. Read the file first and decide:
   - **Is it one document, or several?** A `decisions.md` holding six decisions
     is six `docir add` calls, not one. This is the most common shape in an old
     corpus and the easiest to miss.
   - **Is it still true?** Drafts, superseded decisions and abandoned proposals
     should be added with the right `--status` (or not added at all). A file's
     text may say "superseded by #7" while nothing in its structure does.
   - **What is the real description?** It drives retrieval. The opening
     paragraph is usually context, not a summary — write a better one.
   - **What type is it?** A single bulk-import pass would force one type; a real
     corpus mixes decisions, issues and architecture notes.

   Then add it, stripping any existing YAML frontmatter from the body:
   ```
   docir add --type decision --title "..." --description "..." \
     --status accepted --stdin < old/adr-001.md
   ```
   **Never invent an id.** You may *preserve* one: if the source file already
   carries a number other documents cite, pass it with `--id` so the historical
   cross-references keep resolving.
   ```
   docir add --type decision --id adr-0007 --title "..." --description "..." \
     --status accepted --stdin < old/adr-007.md
   ```
   `--id` is refused if the id is taken or its prefix does not match the type, and
   the next allocation lands past it. It only helps a store using
   `--id-style sequential`; a `random`-style store has no numbering to preserve,
   so let docir assign. Either way, record the returned id for each source file.
4. **Wire relationships in a second pass**, after every doc exists and has an id:
   `docir update <id> --set-related <other-id>:supersedes`. Links can't be set in
   step 3 because every `--related` target must already exist.
5. **Validate**: `docir check` — it flags dangling links, duplicate ids, unknown
   types, and stale docs. Fix those. `orphan` findings just mean a doc has no
   relations yet, which is normal after a migration; don't force links to
   silence them. Wire the ones step 4 missed; where isolation is the right
   answer, say so —
   `docir update <id> --set-isolated "standalone glossary"` — which clears the
   finding without inventing an edge.

## Working across git branches

Only `docs/*.md` + `tags.yaml` are committed; the index is derived and gitignored.
After any merge/pull, and on a fresh clone: `docir reindex` then `docir check`.
The reindex is what rebuilds the index *and* resyncs the id counter from the
files — skip it on a fresh clone and the next `docir add` will refuse to write,
telling you to run it.

`docir init` writes `id_style: random` by default, which mints collision-resistant
ids (`adr-3f9a2b1c7d4e`) so two branches never allocate the same id. A store
created with `--id-style sequential` (or an older schema with no `id_style:` key)
mints readable numbers (`adr-0007`) that are collision-free *within one store* —
but two branches each have their own index and can mint the same number, which
`docir check` reports as `duplicate-id` after the merge. Set `id_style` at the top
of `docs-schema.yaml` for the whole schema, or per type to override it.

