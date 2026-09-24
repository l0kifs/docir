---
paths:
  - "src/docir/modules/release/**"
  - "src/docir/entry_points/doctor.py"
---

# Release detection and `docir self upgrade`

This is the one place docir acts on its own process, so the ordering rules are the feature.

- **The index records which docir built it, and `docir self upgrade` is the command that
  acts on it (adr-31aa7aa60d11).** Migration `0006` adds the one-row `index_build` table,
  written by `reindex` and nothing else — the same single-writer rule the schema baseline
  follows, for the same reason. It is a *separate* table on purpose: the baseline payload is
  diffed line by line and printed, so a version key inside it would render every upgrade as a
  schema change, and the baseline cannot answer this question anyway — it compares schemas, so
  it is silent for a release that changes how documents are *read* (adr-927aa43d9635 rewrote
  every vector without touching a type or a cadence). `stale-index-build` fires on
  **inequality**, not "older than": a downgrade needs the same rebuild. Absent means unknown,
  so a store not rebuilt since the table arrived reports nothing. `self upgrade` runs
  reindex → `agent update` → check in that order (check last, so the findings describe the
  state it left) and **must not gain the package install**: this process is the code that
  would be replaced, so the rebuild after it would stamp the version on its way out. It is a
  `self` group because `docir update <id>` already means "edit a document", and it is not an
  MCP tool — the halves it orchestrates already are.

- **The package half of `self upgrade` re-execs, and refuses to guess (adr-a555ee6bc484).**
  The installer runs only where docir owns its environment — a `uv tool` receipt, pipx
  metadata, a `pyvenv.cfg` — and then `os.execv`s `python -m docir` with a hidden
  `--upgraded-from` (which is also the loop guard), because the process that ran the installer
  is the old build and the reindex after it must not be. A checkout or path install
  (PEP 610 `direct_url.json`), an ephemeral `uvx` env, or anything unrecognised gets no
  command and a reason; the store is still resynced. **The test suite is structurally safe
  because it runs from an editable checkout, which detects as `project`** —
  `test_installation.py` asserts exactly that, and it is the guard that keeps a test from
  replacing the environment it runs in. The release check is opt-in
  (`DOCIR_UPDATE_CHECK=1`, or `update_check: true` in the store's committed `config.yaml`,
  which `docir init` writes), fetched by the daemon at most once a day and *only* read by the
  CLI, so no command ever blocks on the network; `latest` absent means nobody has checked,
  never "up to date"; ordering is `packaging`'s PEP 440, since a hand-rolled compare makes
  0.9.0 newer than 0.10.0.

- **The notice is a decision table, and it is silent where it cannot be acted on
  (adr-bea870d0b666).** `notice_for` is pure and reads `ReleaseStatus`: a `project` install —
  an editable checkout, or a lockfile-managed project — is told **nothing**, because the
  package step of `self upgrade` declines there and this repository is the clearest case; an
  installation with an `upgrade_command` is told to run it *between tasks*, because the
  command re-execs, replaces a mismatched daemon and re-stamps the index; one without carries its own
  `explanation` instead. `announce()` throttles to one release per day per store, recorded in
  `release-check.json` beside the fetched answer — so that file is read-modify-write from two
  processes, and `docir self status` stays the unthrottled answer. Never add a CLI-side
  fetch: the process exits in 0.4–0.7s, PyPI replies in 0.4–0.5s, and a daemon thread dies at
  interpreter exit. MCP puts it in the server's **`instructions`**, which a client reads once on
  connect; no tool result can hold it, because three of them answer with a bare JSON array.

- **An installer that exits 0 is not an installer that upgraded anything
  (issue-f0b537bde01a).** `upgrade_package` reads the environment's version back through the
  `VersionProbe` port after a successful run, and `UpgradeOutcome.version_moved` is
  three-valued — `None` is *could not tell* and must fall through to the re-exec, or a working
  upgrade gets stranded. On `False` there is nothing to hand off to, so the CLI does **not**
  re-exec; it says the version did not move, quotes the installer verbatim, and adds the one
  instruction that holds whatever the cause. The store half still runs and the exit code stays
  0: the package not moving is not a reason to leave the index on the old build.

  **Do not diagnose the cause and do not repair the installation.** The installers already
  explain themselves — `uv tool upgrade` on a pinned receipt prints the pin and the command
  that clears it — and anything docir re-derived would be a worse copy of the text it is
  standing in front of. Rewriting a recorded requirement is worse still: a pin is a *user's*
  instruction, not installer bookkeeping, the receipt does not record why, and
  `uv tool install docir@latest --force` is wrong for four of the five shapes a receipt holds
  (editable, git, plain, pinned). The module's founding rule applies unchanged — a wrong guess
  is worse than no guess.

- **Whether it runs at all is decided in `config/settings.py`, beside the home rule**, for
  the reason both home decisions live there. Precedence: `DOCIR_UPDATE_CHECK` (either
  direction) → `CI` set, which forces it off → the store's `config.yaml`. The store file is
  **committed and appended to, never rewritten** — `init` writes it, `self upgrade` tops it
  up like the `.gitignore`, and a key already present is an answer somebody gave. It is a new
  file rather than a key in `stores.yaml` because an older build cannot fail on a file it
  never opens (adr-36d6156ffab9, adr-ab4598c6f707).
