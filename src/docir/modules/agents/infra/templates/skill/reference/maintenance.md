# Checking and maintaining the corpus

What to do when `docir check` reports something, when a human has edited the
files by hand, and how the staleness signal works. For the *environment* — the
index, the daemon, the model — see [`reference/troubleshooting.md`](troubleshooting.md).

## Contents

- Checks & maintenance — every Tier 1 finding and the command that closes it
- Staleness (`owner` / `verified`) — the review queue, and what verifying means
- What a human may edit by hand — the per-field contract, and what `check` cannot catch

## Checks & maintenance (non-blocking)

- `docir check` — Tier 1 warnings: cycles, orphans, layering, **dangling** `related` links, **duplicate ids**, **stale** docs (past their review cadence), **unknown type/status/tag** (a `type` not in the active schema, a `status` the type doesn't declare, a tag not in the registry — all three mean a file was edited outside the CLI), **missing-required** (a field the type requires that the document lacks), **unknown-relation-kind** (an edge whose kind the schema no longer registers), and **schema-drift** (the schema itself changed since the index was built) and **stale-index-build** (the index was built by a docir that is no longer installed). Run before finishing.
- **`unblocked`** — a live document whose every `depends_on` target has closed. The one
  finding that is good news: it means the work is ready to start. Act on it by starting the
  work or by dropping an edge that is no longer true; nothing clears it mechanically.
- `docir check --strict` — exits nonzero on **error**-severity findings only (`duplicate-id`, `dangling`, `malformed` — the corpus is broken; plus `empty-index`, which means `check` could not look). Use as a **CI / pre-merge gate**, and **run `docir reindex` first**: the index is derived and gitignored, so a fresh clone has none and every structural check reads a blank graph. `empty-index` is what says so rather than letting the gate pass by reading nothing. Warnings (`orphan`, `cycle`, `layering`, `stale`, `unknown-type`, `unknown-status`, `unknown-tag`, `missing-required`, `unknown-relation-kind`, `schema-drift`, `stale-index-build`) are reported but never fail the build; `--strict-all` makes them fatal too.
- **Recovering from `missing-required`**: the schema now requires a field the document was
  written without — usually because `docs-schema.yaml` gained a `required:` entry, or an upgrade
  brought one in through a profile. Supply it (`docir update <id> --set-owner ...`) or drop the
  requirement from the schema. Until then **every** write to that document is refused, including
  one that touches nothing else — so fix these before editing an old document.
- **Recovering from `unknown-type`** (a doc whose `type` isn't in the active schema, usually
  because a profile was disabled): re-enable the profile in `docs-schema.yaml`, or change the
  doc's `type` to one the schema knows — then `docir reindex`. `check --fix` deliberately will
  not guess which you meant. Until it is resolved the doc cannot be validated, is never
  reported stale, and is skipped by the layering check.
- `docir doctor` — the *environment*, not the corpus: the installation, this store's derived
  index, the embedding model in force, the daemon, and each declared peer. See `reference/troubleshooting.md`. Run it when a read contradicts the files, and once after cloning a repo.
  **In CI, run it after `docir reindex` and before `docir check --strict`** — the index is
  gitignored, so without the rebuild `check` runs over zero documents and reports a clean
  corpus; `doctor --strict` is what proves the rebuild populated it.
- `docir check --fix` — repair what can be repaired without guessing: re-issue duplicate ids (the oldest file keeps the id, so existing links stay valid) and drop `related` edges pointing at nothing. It reports every change, then lists what it could not fix. `malformed` and `unknown-type` are left alone — those need you to decide what the file or the schema should say. **This is the supported way to recover; do not hand-edit markdown to fix these.**
- **Recovering from `schema-drift`**: the active schema differs from the one the index was built
  against — usually an upgrade, since the types, statuses and cadences come from the installed
  docir as much as from `docs-schema.yaml`. Each finding names one change (`+type test_plan`,
  `type decision: required [] -> ['owner']`). Deal with the consequences it explains — the
  `unknown-type`, `unknown-status` and `missing-required` findings beside it — then `docir
  reindex`, which is what records the new baseline. Set `DOCIR_SCHEMA_NOTICE=1` to have every
  command print the drift on stderr instead of waiting for a `check`.
- **`docir self upgrade` — upgrade docir and resync this store, in one command.** It
  installs the newest docir where docir owns its environment (a uv tool, a pipx install, a
  virtualenv), re-executes as the new build, then reindexes (the index is derived and
  gitignored, and a rebuild is what records the schema baseline *and* the version that built
  it), refreshes any installed agent instruction file, and reports what `check` still finds.
  Where docir does *not* own its environment — a checkout, a project whose lockfile pins it,
  an ephemeral `uvx` run — it says so on stderr and does the rest; the package is that
  project's to upgrade. Pass `--no-package` to skip the install and only resync the store.
  **`stale-index-build`** is the finding that asks for this: the index was built by a docir
  that is no longer installed. A warning, never a `--strict` failure — every store is in that
  state between an upgrade and the next rebuild.
- `docir self status` — what is installed, how, and whether a newer release exists. A file
  read: it reports the answer the daemon last cached, and an absent `latest` means *nobody
  has checked*, not "up to date". `--refresh` asks PyPI now (docir's only network call, and
  it is skipped if the answer is already from today). Set `DOCIR_UPDATE_CHECK=1` to have the
  daemon keep it fresh and every command say on stderr when a newer docir is out.
- `docir lint --deep` — Tier 2 advisories: duplicate content, oversized documents,
  **oversized sections** (a section the chunker has to split, so part of it is text no
  heading can address), **ambiguous headings** (used twice in one document, so a section
  read reaches only the first), and **unqualified section references** (prose naming a
  section that lives in another document). All advisory — a long reference table is often
  right as it is.
  Also **broken expressions** — a `--expr` documented in a body that would not run, which
  is the one documented argument that is a language rather than a flag.
- `docir reindex [--changed]` — after a doc file was hand-edited, merged, or freshly cloned.
  `--changed` only skips re-saving files whose content is unchanged; deleted files are swept
  from the index either way, so both modes leave the index agreeing with the filesystem.
  **Read `documents_skipped` in the output.** A file whose frontmatter does not parse is
  skipped, not indexed — it exists on disk and is invisible to every read path. Non-zero
  means run `docir check` and fix the named file before trusting a search.

## Staleness (`owner` / `verified`)

For docs that need periodic re-confirmation, set an `--owner` and, when you
(or a human) confirm a doc is still correct, run `docir update <id> --verified`.
A type's review cadence (`review_days` in the schema) drives a non-blocking
`stale` warning in `docir check` and a `stale` flag on read views. Editing the
body does not equal verifying it — `--verified` is the explicit signal.

Pull the review queue rather than reading `check` output for it:

```
docir query --stale                          # everything overdue
docir query --owner platform-team --stale    # one steward's queue
```

`--stale` is applied before `--limit`, so the limit counts overdue docs. Work the
queue by reading each one (`docir get <id>`), then either fixing it or, if it is
still correct, `docir update <id> --verified`.

**Stale is not the same as wrong.** It means nobody has vouched for the doc
within its cadence. Never mark `--verified` on a doc you have not actually read —
that is the one signal the whole mechanism rests on, and stamping it blind makes
the corpus look reviewed when it is not.

## What a human may edit by hand

You must not — every write goes through the CLI. A human working in the repo
will, though, and the rules differ per field. If you are asked to reconcile a
hand-edited corpus, this is the contract:

| file / field | by hand? | why |
|---|---|---|
| a document's **body** (below the `---`) | ✅ yes | Prose. `reindex` picks it up; nothing else depends on it. |
| `docs-schema.yaml` | ✅ yes | No CLI write path exists — this is the intended way. |
| `docs/tags.yaml` | ✅ yes | A `key: description` mapping; `reindex` loads it. `docir tag add` is easier. |
| `title` / `description` | ⚠️ prefer CLI | Works, but they drive retrieval — `--set-description` also re-embeds. |
| `tags` | ❌ use `docir update --set-tags` | An unregistered tag is a Tier 0 error the CLI would catch; by hand it silently isn't (`check` reports `unknown-tag`). |
| `status` | ❌ use `docir update --status` | Bypasses the transition rules; a status the type doesn't declare leaves the doc with no legal exit (`check` reports `unknown-status`). |
| `related` | ❌ use `docir update --set-related` | Targets must exist and kinds must be registered; by hand you get `dangling` or `unknown-relation-kind` instead. |
| `type` | ❌ | Must be in the schema, and the id prefix already encodes it (`check` reports `unknown-type`). |
| `id` | ❌ **never** | It is the primary key. Changing it orphans every inbound link and can duplicate a live id. |
| `created` / `updated` | ❌ | `updated` is the staleness clock's fallback. |
| `verified` | ❌ **never** | It means "somebody re-read this and it is still true". Nothing can check that, so writing it by hand is simply a false statement. Use `docir update <id> --verified`. |

**After any hand-edit: `docir reindex` then `docir check`.** Reindex reports
`documents_skipped` for files whose frontmatter will not parse — those are
*absent from every read path*, not merely flagged. `check` then catches
`unknown-tag`, `unknown-status`, `unknown-type`, `unknown-relation-kind`,
`missing-required`, `dangling` and `duplicate-id`.

It cannot catch everything: a plausible-but-wrong `verified` date, or edited
`created`/`updated`, are indistinguishable from real ones. Those are the fields
to leave alone.

