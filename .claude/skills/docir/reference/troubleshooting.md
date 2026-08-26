<!-- docir:v0.19.0 — generated file, do not edit by hand; refresh with `docir agent update` after upgrading docir -->
# When the answers look wrong

Reads can quietly answer from the wrong state, and every such condition looks
exactly like a correct answer. This file is the environment half; the corpus half
— dangling edges, duplicate ids, staleness — is [`reference/maintenance.md`](maintenance.md).

## Contents

- `docir doctor` — every finding and the command that closes it
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
  → `docir self upgrade`
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

## Notes

- Errors print `error: <message>` to **stderr** with a nonzero exit code (2=validation, 4=not-found, 5=conflict, 6=stale), so a captured stdout stays clean JSON.
- Vectors are computed async; add `--wait-embeddings` to a write (or `docir embed --flush`) if you must `context`-search immediately after.
- `docir context` matches on meaning, not just wording, so describe the task in your own words rather than guessing the documents' vocabulary. (If the store runs `DOCIR_EMBEDDER=deterministic` — a light, model-free fallback — matching is vocabulary-based instead; when a query under-retrieves there, retry with the terms the codebase actually uses.)
- All state lives under `~/.docir` (override `DOCIR_HOME`); the index is disposable and rebuildable from files.
