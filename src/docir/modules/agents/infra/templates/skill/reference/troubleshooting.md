# When the answers look wrong

Reads can quietly answer from the wrong state, and every such condition looks
exactly like a correct answer. This file is the environment half — the index, the
daemon, the model, the installation. The corpus half — dangling edges, duplicate
ids, staleness — is [`reference/maintenance.md`](maintenance.md).

## Contents

- `docir doctor` — every finding and the command that closes it
- Keeping the installation current — `docir self upgrade`, `docir self status`
- Notes — exit codes, async vectors, where state lives

## `docir doctor` first

One command reports every such condition:

```bash
docir doctor            # the whole report; no network, no model load, ~100ms
docir doctor --strict   # exit 1 on error-severity findings only (setup scripts, CI)
docir doctor --probe    # also load the embedding model and time it (may download ~67MB)
```

Each finding carries a `kind`, a `severity` and the command that closes it:

- `no-index` / `empty-index` — the index is derived and **gitignored**, so a fresh clone has
  none and every read answers nothing. Both are errors, and `empty-index` is the one that
  survives: opening the store creates the file, so the *second* command finds an empty index
  rather than a missing one. `docir check` reports `empty-index` too, for the same reason —
  its structural checks read that empty graph. → `docir reindex`
- `index-behind-files` — the index holds fewer documents than `docs/` does. A warning: usually
  one file that will not parse, which `docir check` names as `malformed`.
- `stale-index-build` — the index was built by a docir that is no longer installed.
  → `docir self upgrade` (below)
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
- `docir self status` — what is installed, how, and whether a newer release exists. A file
  read: it reports the answer the daemon last cached, and an absent `latest` means *nobody
  has checked*, not "up to date". `--refresh` asks PyPI now (docir's only network call, and
  it is skipped if the answer is already from today). Set `DOCIR_UPDATE_CHECK=1` to have the
  daemon keep it fresh and every command say on stderr when a newer docir is out.

## Notes

- Errors print `error: <message>` to **stderr** with a nonzero exit code (2=validation, 4=not-found, 5=conflict, 6=stale), so a captured stdout stays clean JSON.
- `no document with id '<id>'` from `get` or `update` means what it says only when the message stops there. When the index holds nothing while `docs/` holds files — a fresh clone, a new `git worktree` — it names that instead and asks for `docir reindex`; the document is on disk and nothing was lost. Do not go looking for a deletion, and do not rewrite the document: rebuild the index and repeat the command.
- Vectors are computed async; add `--wait-embeddings` to a write (or `docir embed --flush`) if you must `context`-search immediately after.
- `docir context` matches on meaning, not just wording, so describe the task in your own words rather than guessing the documents' vocabulary. (If the store runs `DOCIR_EMBEDDER=deterministic` — a light, model-free fallback — matching is vocabulary-based instead; when a query under-retrieves there, retry with the terms the codebase actually uses.)
- All state lives under `~/.docir` (override `DOCIR_HOME`); the index is disposable and rebuildable from files.
