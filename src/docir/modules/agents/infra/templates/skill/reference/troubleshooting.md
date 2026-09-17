# When the answers look wrong

Reads can quietly answer from the wrong state, and every such condition looks
exactly like a correct answer. This file is the environment half — the index, the
daemon, the model, the installation. The corpus half — dangling edges, duplicate
ids, staleness — is [`reference/maintenance.md`](maintenance.md).

## Contents

- `docir doctor` — every finding and the command that closes it
- A store written by a newer docir — what it looks like, and the repair to refuse
- Keeping the installation current — `docir self upgrade`, `docir self status`
- When docir itself is the defect — report it, do not route around it
- Notes — exit codes, async vectors, where state lives

## `docir doctor` first

One command reports every such condition:

```bash
docir doctor            # the whole report; no network, no model load, ~100ms
docir doctor --strict   # exit 1 on error-severity findings only (setup scripts, CI)
docir doctor --probe    # also load the embedding model and time it (may download ~67MB)
```

Each finding carries a `kind`, a `severity` and the command that closes it:

- `no-index` — there was no index when the command started. A **warning**, in the past tense:
  the index is derived and **gitignored**, so a fresh clone and every new `git worktree` has
  none, and opening the store rebuilds it from the files. Run `docir reindex` only to compute
  the vectors that rebuild defers.
- `empty-index` — an index holding nothing while `docs/` holds files, which the rebuild above
  did not reach: a store opened before its files arrived, or by an older docir. Still an
  **error**, because every read answers nothing. `docir check` reports it too, since its
  structural checks read that empty graph. → `docir reindex`
- `index-behind-files` — the index holds fewer documents than `docs/` does. A warning: usually
  one file that will not parse, which `docir check` names as `malformed`.
- `stale-index-build` — the index was built by a docir that is no longer installed.
  → `docir self upgrade` (below)
- `index-from-newer-build` — a newer docir opened this store and migrated the index past
  what this build ships. The mirror image of `stale-index-build`, and an **error**: every
  command that opens the index refuses (exit 8), `reindex` included. Two builds are
  sharing one store, so run the newer one — or delete `.docir/index.db*` and
  `docir reindex` to rebuild at this build's schema, knowing the newer build migrates it
  again the next time it runs. Nothing is lost either way; the index is derived.
- `schema-drift` — the types or cadences moved under the corpus with nothing in `git diff`.
  → `docir check` to read them, then `docir reindex`
- `hashing-embedder` / `embeddings-pending` — `DOCIR_EMBEDDER` is overriding the model, or
  documents have no current vector, so `docir context` is ranking blind.
  → unset it, then `docir embed --flush`
- `stale-daemon` — the daemon was serving code this process is not running. Already replaced by
  the doctor run; **re-run anything you acted on**.
- `peer-unavailable` — a store in `stores.yaml` that every federated read is silently skipping.
- `global-fallback` / `shadowed-store` — writes are about to land in a store other than the one
  you think. → `docir init`

`error` means docir cannot work correctly here (no index, a schema that will not load, no
embedding model); `warning` means it works less well than you think. Only `error` fails
`--strict`.

The corpus is a different question: `docir doctor` never scans the graph, and `docir check` is
what reports dangling edges, duplicate ids and staleness.

## A store written by a newer docir

A store is a committed artifact, so the docir reading it is not always the one
that wrote it. Most of that skew is harmless — an older build ignores a
frontmatter field or a schema key it does not know. Two shapes are not, and both
look like a broken repository rather than an old binary.

**`error: type '<name>' must define a string 'prefix'`, on every command.** The
store uses a schema *overlay* — a `types:` block that deliberately omits
`prefix` / `statuses` / `default_status` so the rest of the type keeps coming
from the core or a profile. A build predating that form reads the block as a
malformed declaration — and since no command can run without resolving the
schema first, the failure is total: `docir get`, `docir query`, `docir check`,
all of them, with an empty payload and exit 3.

**Do not add the missing keys.** The message names the repair that breaks the
store quietly: writing all three turns the overlay into a full declaration,
which takes the type over — the file then owns that type, stops inheriting
anything later releases change, and nothing reports the divergence afterwards.
You would be committing that to everybody else's checkout too.

Tell it apart from a genuinely broken schema with the one command that still
runs:

```bash
docir doctor          # snapshots the environment BEFORE opening the store
```

It reports `schema-unreadable` next to `installation.version`. If that version
is older than the one the store's teammates run, the store is fine and the
binary is behind:

```bash
docir self upgrade    # where docir owns its environment
```

Inside a repository that pins docir (a lockfile, a checkout), run the project's
own build instead — `uv run docir ...` — rather than a globally installed one,
which is how this mismatch usually arises.

**`index-from-newer-build`** is the same story for the index rather than the
schema, and `docir doctor` names it directly; the entry above says what to do.

## Keeping the installation current

- **`docir self upgrade` — upgrade docir and resync this store, in one command.** It
  installs the newest docir where docir owns its environment (a uv tool, a pipx install, a
  virtualenv), re-executes as the new build, then reindexes (the index is derived and
  gitignored, and a rebuild is what records the schema baseline *and* the version that built
  it), refreshes any installed agent instruction file, and reports what `check` still finds.
  Where docir does *not* own its environment — a checkout, a project whose lockfile pins it,
  an ephemeral `uvx` run — it says so on stderr and does the rest; the package is that
  project's to upgrade. Pass `--no-package` to skip the install and only resync the store.
  `stale-index-build` is the finding that asks for this. It is a warning, never a `--strict`
  failure — every store is in that state between an upgrade and the next rebuild.
- **Upgrading before your teammates is normal, and costs them two things.** The store is
  committed, so they keep reading it — but their *first* command fails, because the index this
  build migrated is one theirs does not ship. The message names both revisions and the fix, and
  a plain `docir reindex` is not it: that opens the index too, and refuses for the same reason.
  They delete `index.db*` and reindex, once. Nothing in `docs/` is touched and nothing is lost.
  Then, until they upgrade, each of their writes silently drops the frontmatter keys their
  build does not know — a `code_baseline:` today — so a document they edit quietly stops being
  watched. Run `docir check --fix` after; it refiles what was dropped and names every document
  it touched. If you would rather not manage that, upgrade together.
- `docir self status` — what is installed, how, and whether a newer release exists. A file
  read: it reports the answer the daemon last cached, and an absent `latest` means *nobody
  has checked*, not "up to date". `--refresh` asks PyPI now (docir's only network call, and
  it is skipped if the answer is already from today). Set `DOCIR_UPDATE_CHECK=1` to have the
  daemon keep it fresh and every command say on stderr when a newer docir is out.

## When docir itself is the defect

Some failures survive `doctor`, `reindex` and an upgrade because they are docir's,
not this store's. The cheap response is a local workaround, and it is the wrong one:
a wrapper script around a wrong output, a project rule saying "docir gets X wrong, so
always do Y", a hand-edited `docs/*.md` because a flag is missing, a pinned older
version, a second source of truth docir cannot hold. Each is a private fix for a
public bug — it keeps failing for everyone else, and it deletes the evidence.

So when you catch yourself about to write one: **stop and tell the human what docir
did, what you expected, and what the workaround would cost.** Write the workaround
too if the task needs it today — but say it is one.

If they want it reported upstream, docir ships an opt-in skill that does it properly
(reproduce on a throwaway store, redact, draft a report they review and file):

```bash
docir agent install --agent claude-feedback
```

It is never installed by default and it never sends anything itself. Anything
exploitable goes to a private advisory instead, never a public issue.

## Notes

- Errors print `error: <message>` to **stderr** with a nonzero exit code (2=validation, 4=not-found, 5=conflict, 6=stale, 8=index unreadable by this build), so a captured stdout stays clean JSON.
- `no document with id '<id>'` from `get` or `update` means what it says only when the message stops there. When the index holds nothing while `docs/` holds files it names that instead and asks for `docir reindex`; the document is on disk and nothing was lost. Opening a store normally rebuilds an index it finds empty, so this is the rare leftover — an index emptied under a running daemon. Do not go looking for a deletion and do not rewrite the document: rebuild the index and repeat the command.
- `daemon failed to become ready in time` quotes what the daemon wrote while failing — usually the last lines of its traceback, which name the cause. Read those rather than the timeout: the wait is the symptom. When it says the daemon **wrote nothing**, it did not get far enough to fail out loud, which points at the spawn rather than at the store; `docir --no-daemon <cmd>` runs the same command in process and reports the real error directly.
- Vectors are computed async; add `--wait-embeddings` to a write (or `docir embed --flush`) if you must `context`-search immediately after.
- `docir context` matches on meaning, not just wording, so describe the task in your own words rather than guessing the documents' vocabulary. (If the store runs `DOCIR_EMBEDDER=deterministic` — a light, model-free fallback — matching is vocabulary-based instead; when a query under-retrieves there, retry with the terms the codebase actually uses.)
- All state lives under `~/.docir` (override `DOCIR_HOME`); the index is disposable and rebuildable from files.
