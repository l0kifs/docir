<!-- docir:v0.23.0 — generated file, do not edit by hand; refresh with `docir agent update` after upgrading docir -->
# Checking and maintaining the corpus

What to do when `docir check` reports something, when a human has edited the
files by hand, and how the staleness signal works. For the *environment* — the
index, the daemon, the model, the installation — see
[`reference/troubleshooting.md`](troubleshooting.md).

## Contents

- Checks & maintenance — every Tier 1 finding and the command that closes it
- Staleness (`owner` / `verified`) — the review queue, and what verifying means
- What a human may edit by hand — the per-field contract, and what `check` cannot catch

## Checks & maintenance (non-blocking)

- `docir check` — Tier 1 warnings over the corpus: `cycle`, `orphan`, `layering`,
  **`dangling`** (a `related` link pointing at nothing), **`duplicate-id`**, **`stale`** (past
  the type's review cadence), **`unknown-type`** / **`unknown-status`** / **`unknown-tag`** /
  **`unknown-relation-kind`** (a type, status, tag or relation kind the schema does not know —
  all four mean a file was edited outside the CLI), **`missing-required`**, **`schema-drift`**
  and **`stale-index-build`**. Run before finishing; the ones worth a recovery are spelled out
  below.
- **Recovering from `orphan`** — two exits, and `SKILL.md` says which to reach for:
  `docir update <id> --set-related <other>:refines`, or
  `docir update <id> --set-isolated "no acceptance criterion references this flow"`. Audit the
  exemptions with `docir query --expr "isolated"`; `--set-isolated ""` puts a document back in
  the queue. Nothing mechanical closes this finding.
- **`unblocked`** — a live document whose every `depends_on` target has closed. The one
  finding that is good news: it means the work is ready to start. Act on it by starting the
  work or by dropping an edge that is no longer true; nothing clears it mechanically.
- `docir check --strict` — exits nonzero on **error** severity only: `duplicate-id`,
  `dangling`, `malformed` (the corpus is broken) plus `empty-index` (`check` could not look).
  Every other finding above is a warning and never fails the build; `--strict-all` makes them
  fatal too.
  **As a CI / pre-merge gate the order is `docir reindex` → `docir doctor --strict` →
  `docir check --strict`.** The explicit rebuild is what computes the vectors — a store opened
  cold defers them (`reference/troubleshooting.md`, `no-index`) — so the order stands.
  `doctor --strict` proves the index is populated, and `empty-index` is what fires if it is not.
- **Recovering from `missing-required`** — the type requires a field the document was written
  without, usually because `docs-schema.yaml` gained a `required:` entry or an upgrade brought
  one in through a profile. Supply it (`docir update <id> --set-owner ...`) or drop the
  requirement from the schema. Until then **every** write to that document is refused, including
  one that touches nothing else — so fix these before editing an old document.
- **Recovering from `unknown-type`** — the document's `type` is not in the active schema,
  usually because a profile was disabled. Re-enable the profile in `docs-schema.yaml`, or
  change the doc's `type` to one the schema knows — then `docir reindex`. `check --fix` deliberately will
  not guess which you meant. Until it is resolved the doc cannot be validated, is never
  reported stale, and is skipped by the layering check.
- `docir doctor` — the *environment* rather than the corpus, and a different question: run it
  when a read contradicts the files, and once after cloning a repo. Every finding it can
  report, and the command that closes each, is in `reference/troubleshooting.md`.
- `docir check --fix` — repair what needs no guess: re-issue duplicate ids (the oldest file
  keeps the id, so existing links stay valid) and drop `related` edges pointing at nothing. It
  reports every change, then lists what it could not fix. `malformed` and `unknown-type` are
  left alone — those need you to decide what the file or the schema should say. **This is the
  supported way to recover; do not hand-edit markdown to fix these.**
- **Recovering from `schema-drift`** — the schema moved under the corpus since the index was
  built, usually an upgrade: the types, statuses and cadences come from the installed docir as
  much as from `docs-schema.yaml`. Each finding names one change (`+type test_plan`,
  `type decision: required [] -> ['owner']`). Deal with the consequences it explains — the
  `unknown-type`, `unknown-status` and `missing-required` findings beside it — then `docir
  reindex`, which is what records the new baseline. Set `DOCIR_SCHEMA_NOTICE=1` to have every
  command print the drift on stderr instead of waiting for a `check`.
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
body does not equal verifying it — `--verified` is the explicit signal, and the
only thing that clears an entry.

The cadence is measured against the `verified` stamp; with no stamp, against
`created`. **An edit is not a stamp** — write a re-check into an overdue doc and
it stays overdue, which is what makes "asked again, no answer" safe to record.
Write the note; stamp `--verified` only once somebody has actually confirmed the
doc is correct.

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

**After any hand-edit: `docir reindex` then `docir check`.** Watch `documents_skipped`
in the reindex output (above). `check` then catches `unknown-tag`, `unknown-status`,
`unknown-type`, `unknown-relation-kind`, `missing-required`, `dangling` and
`duplicate-id`.

It cannot catch everything: a plausible-but-wrong `verified` date, or edited
`created`/`updated`, are indistinguishable from real ones. Those are the fields
to leave alone.

