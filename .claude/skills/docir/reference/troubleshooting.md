<!-- docir:v0.29.0 — generated file, do not edit by hand; refresh with `docir agent update` after upgrading docir -->
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
- `no-daemon-socket` — there is no usable temporary directory, so the daemon cannot run here at
  all. This is the sandbox case, and nothing is broken: every command still answers, in process,
  paying the model's cold start. → set `TMPDIR` to a writable directory, or `DOCIR_NO_DAEMON=1`
  to stop trying and silence the per-command notice.
- `embedding.threads` is not a finding but is the line to read when docir is loading the
  machine: `null` means uncapped, which is fastembed's default of every core.
  → `DOCIR_EMBED_THREADS`, which SKILL.md covers — what to set it to, and when.
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
  it is skipped if the answer is already from today).
- **A newer docir announces itself, once.** A store created by `docir init` carries
  `update_check: true` in its `config.yaml`, so the daemon refreshes the answer daily and a
  command prints one line on stderr — over MCP it arrives in the server's instructions at the
  handshake instead. You will see it at most once a day per release.

  **Act on it between tasks, never inside one.** `docir self upgrade` installs the new
  package, replaces the running process, respawns the daemon and rebuilds the index; a task
  that continues across that runs its remaining steps on a build nothing has verified, and in
  CI it makes the job depend on the day it ran. Finish what you are doing, then run it — and
  read the `check` findings it prints, because a release that moves the schema leaves work.

  The notice is deliberately silent where it would be useless: a docir installed from a
  checkout or pinned by a project lockfile is upgraded in that project, not by this command,
  and it is told nothing. If you suspect you are behind and saw no notice, ask directly with
  `docir self status --refresh`.

- **When `docir self upgrade` reports that the installer ran and the version did not move**,
  the package manager held it back. It is not a failure and the store half still ran; the
  package simply did not change.

  docir prints the installer's own words directly underneath, and for most holds that text
  names the command that releases it — a `uv tool` install pinned to an exact version prints
  the `uv tool install docir@latest` form to reinstall with. Run whatever it names, then
  `docir self upgrade --no-package` to bring the store to the build you now have.

  Some installers explain nothing: a pip held back by a constraint file exits 0 silently. Then
  read `docir self status` — `method` says how this docir arrived and `upgrade_command` says
  what docir would run — and resolve it there. Never work around it by editing files docir
  owns or by pinning the store to an older shape; report it instead.

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
- `warning: the daemon could not be started` on stderr means the command still ran — in process, paying a cold model load, with stdout unaffected. The daemon keeps the model warm and serializes writes and decides nothing, so it is an accelerator you are doing without, not a failure. The reason follows the warning: a sandbox that denies the socket or the log directory is the common one, and `DOCIR_NO_DAEMON=1` skips the attempt (and the notice) for the rest of the session. Where the reason is `daemon failed to become ready in time`, it quotes what the daemon wrote while failing — usually the last lines of its traceback, which name the cause; read those rather than the timeout, since the wait is the symptom. **Wrote nothing** means it did not get far enough to fail out loud, which points at the spawn rather than at the store.
- Vectors are computed async; add `--wait-embeddings` to a write (or `docir embed --flush`) if you must `context`-search immediately after.
- `docir context` matches on meaning, not just wording, so describe the task in your own words rather than guessing the documents' vocabulary. (If the store runs `DOCIR_EMBEDDER=deterministic` — a light, model-free fallback — matching is vocabulary-based instead; when a query under-retrieves there, retry with the terms the codebase actually uses.)
- All state lives under `~/.docir` (override `DOCIR_HOME`); the index is disposable and rebuildable from files. The embedding model is the exception to "per store": it is one 64 MB copy per machine in `~/.docir/models`, overridable with `FASTEMBED_CACHE_PATH`, and `docir doctor` reports the path under `embedding.cache` — which is the answer to "why did that command take sixteen seconds" when a download has just been re-paid.
